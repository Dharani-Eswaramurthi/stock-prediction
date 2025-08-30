from datetime import date, timedelta
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import upstox_client
import requests
import asyncio
import websockets
from google.protobuf.json_format import MessageToDict
import backend.MarketDataFeedV3_pb2 as pb
import ssl
import json

from backend.config import CORS_ORIGINS, BACKEND_HOST, BACKEND_PORT, OPENAI_API_KEY
from backend.data_source import (
    get_authorize_url,
    exchange_code_for_token,
    set_access_token,
    is_authenticated,
    get_instruments,
    get_historical_candles,
    get_access_token,
)
from services.indicators import add_indicators
from services.openai_signals import get_trade_signal

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OAuthStartResponse(BaseModel):
    url: str


@app.get("/auth/start", response_model=OAuthStartResponse)
async def auth_start():
    return {"url": get_authorize_url()}


@app.get("/auth/callback")
async def auth_callback(code: str = Query(...)):
    try:
        token = exchange_code_for_token(code)
        print("TOKEN:", token)
        set_access_token(token)
        # Return a small HTML page that closes the popup and notifies the opener
        html = """
        <!DOCTYPE html>
        <html>
          <head>
            <meta charset=\"utf-8\" />
            <title>Upstox Auth</title>
          </head>
          <body style=\"font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; padding: 24px;\">
            <h3>Authentication successful</h3>
            <p>You can close this tab.</p>
            <script>
              try {
                if (window.opener) {
                  window.opener.postMessage({ type: 'UPSTOX_AUTH', status: 'ok' }, '*');
                }
              } catch (e) {}
              setTimeout(function(){ window.close(); }, 300);
            </script>
          </body>
        </html>
        """
        return HTMLResponse(content=html)
    except Exception as e:
        html = f"<html><body><h3>Auth error</h3><pre>{{str(e)}}</pre><script>setTimeout(function(){{ window.close(); }}, 2000);</script></body></html>"
        return HTMLResponse(content=html, status_code=400)

@app.get("/auth/status")
async def auth_status():
    if is_authenticated():
        return {"authenticated": True, "access_token": get_access_token()}
    return {"authenticated": False}


@app.get("/instruments")
async def instruments(exchange: Optional[str] = None, q: Optional[str] = None, limit: int = 50):
    df = get_instruments(exchange=exchange, query=q, limit=limit)
    keep = ["segment", "trading_symbol", "instrument_key", "instrument_type", "name"]
    sub = df[[c for c in keep if c in df.columns]]
    return sub.to_dict(orient="records")


class CandlesRequest(BaseModel):
    instrument_key: str
    interval: str  # day, week, month, 30minute, 1minute
    from_date: Optional[date]
    to_date: date


@app.post("/candles")
async def candles(body: CandlesRequest):
    # Max lookback windows aligned with Upstox constraints
    # minutes 1–15: ~1 month; minutes >15 (e.g., 30): ~1 quarter; days: ~1 decade; week/month: cap at 10 years
    interval_allowed = {"1minute": 30, "30minute": 90, "day": 3650, "week": 3650, "month": 3650}
    if body.interval not in interval_allowed:
        raise HTTPException(status_code=400, detail="Invalid interval")
    max_lookback_days = interval_allowed[body.interval]

    # Map UI interval to Upstox v3 unit + interval
    unit_interval_map = {
        "1minute": ("minutes", "1"),
        "30minute": ("minutes", "30"),
        "day": ("days", "1"),
        "week": ("weeks", "1"),
        "month": ("months", "1"),
    }
    unit, numeric_interval = unit_interval_map[body.interval]

    # Normalize dates
    end = body.to_date
    start = body.from_date or (end - timedelta(days=max_lookback_days - 1))

    # Ensure chronological order
    if start > end:
        start, end = end, start

    # Clamp start to allowed range
    min_allowed = end - timedelta(days=max_lookback_days - 1)
    if start < min_allowed:
        start = min_allowed

    df = get_historical_candles(
        instrument_key=body.instrument_key,
        unit=unit,
        interval=numeric_interval,
        to_date=end.isoformat(),
        from_date=start.isoformat() if start else None,
    )
    if df.empty:
        return {"candles": []}
    return {"candles": df.assign(time=lambda d: d["time"].astype(str)).to_dict(orient="records")}


class SignalRequest(BaseModel):
    instrument_key: str
    symbol: str
    candles: list[dict]
    # Optional analysis context
    horizon: str | None = None  # e.g., next 30min, 1h, 1d, 1w
    analysis_interval: str | None = None  # 1minute, 30minute, day, week
    from_date: str | None = None
    to_date: str | None = None


@app.post("/signal")
async def signal(body: SignalRequest):
    df = pd.DataFrame(body.candles)
    if df.empty:
        raise HTTPException(status_code=400, detail="No candles provided")
    df["time"] = pd.to_datetime(df["time"])  # parse back
    df = add_indicators(df)
    resp = get_trade_signal(
        symbol=body.symbol,
        instrument_key=body.instrument_key,
        candles=df,
        horizon=body.horizon,
        analysis_interval=body.analysis_interval,
        from_date=body.from_date,
        to_date=body.to_date,
    )
    return resp

def get_market_data_feed_authorize_v3(access_token: str):
    """Get authorization for market data feed."""
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    url = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
    api_response = requests.get(url=url, headers=headers)
    api_response.raise_for_status()
    return api_response.json()["data"]["authorized_redirect_uri"]


def decode_protobuf(buffer):
    """Decode protobuf message."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response


@app.websocket("/ws/ltp_v3")
async def ws_ltp_v3(ws: WebSocket):
    await ws.accept()
    params = dict(ws.query_params)
    inst_key = params.get("instrument_key")
    token = params.get("access_token")

    if not inst_key or not token:
        await ws.close(code=1003)
        return

    try:
        # Step 1: Get the authorized websocket URL
        wss_url = get_market_data_feed_authorize_v3(token)

        # Step 2: Connect to Upstox feed
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with websockets.connect(wss_url, ssl=ssl_context) as upstream:
            print("Connected to Upstox Market Data Feed")

            # Step 3: Subscribe to *selected* instrument
            sub_req = {
                "guid": "fastapi-ws",
                "method": "sub",
                "data": {
                    "mode": "full",
                    "instrumentKeys": [inst_key]
                }
            }
            await upstream.send(json.dumps(sub_req).encode("utf-8"))

            # Step 4: Relay messages from Upstox to UI client
            while True:
                raw_msg = await upstream.recv()
                decoded = decode_protobuf(raw_msg)
                data_dict = MessageToDict(decoded)
                await ws.send_json(data_dict)

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print("Stream error:", e)
        await ws.close()



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)
