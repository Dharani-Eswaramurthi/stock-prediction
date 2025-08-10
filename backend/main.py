from datetime import date, timedelta
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import CORS_ORIGINS, BACKEND_HOST, BACKEND_PORT
from backend.services.data_source import (
    get_authorize_url,
    exchange_code_for_token,
    set_access_token,
    is_authenticated,
    get_instruments,
    get_historical_candles,
    get_stream_runner,
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
        set_access_token(token)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/auth/status")
async def auth_status():
    return {"authenticated": is_authenticated()}


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


@app.post("/signal")
async def signal(body: SignalRequest):
    df = pd.DataFrame(body.candles)
    if df.empty:
        raise HTTPException(status_code=400, detail="No candles provided")
    df["time"] = pd.to_datetime(df["time"])  # parse back
    df = add_indicators(df)
    resp = get_trade_signal(symbol=body.symbol, instrument_key=body.instrument_key, candles=df)
    return resp


@app.websocket("/ws/ltp")
async def ws_ltp(ws: WebSocket):
    await ws.accept()
    params = dict(ws.query_params)
    instrument_key = params.get("instrument_key")
    if not instrument_key:
        await ws.close(code=1003)
        return

    def forward(msg):
        try:
            import json
            data = msg if isinstance(msg, dict) else {"raw": str(msg)}
            import anyio
            anyio.from_thread.run(ws.send_text, json.dumps(data))
        except Exception:
            pass

    try:
        get_stream_runner(instrument_key, forward)
        while True:
            await ws.receive_text()
    except Exception:
        await ws.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)