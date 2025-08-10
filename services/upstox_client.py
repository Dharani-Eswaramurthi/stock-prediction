import os
import threading
from datetime import datetime
from typing import Callable, Optional

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

try:
    import upstox_client
except Exception:  # not installed yet
    upstox_client = None  # type: ignore

UPSTOX_AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
INSTRUMENTS_JSON_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json"

_access_token: Optional[str] = None


def _require_token() -> str:
    if not _access_token:
        raise RuntimeError("Upstox access token not set. Login first.")
    return _access_token


def get_authorize_url() -> str:
    client_id = os.getenv("UPSTOX_CLIENT_ID")
    redirect_uri = os.getenv("UPSTOX_REDIRECT_URI")
    if not client_id or not redirect_uri:
        raise RuntimeError("Missing UPSTOX_CLIENT_ID or UPSTOX_REDIRECT_URI in env.")
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    return f"{UPSTOX_AUTH_URL}?" + requests.compat.urlencode(params)


def exchange_code_for_token(code: str) -> str:
    client_id = os.getenv("UPSTOX_CLIENT_ID")
    client_secret = os.getenv("UPSTOX_CLIENT_SECRET")
    redirect_uri = os.getenv("UPSTOX_REDIRECT_URI")
    if not (client_id and client_secret and redirect_uri):
        raise RuntimeError("Missing UPSTOX env vars.")

    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    headers = {"accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError(f"Token exchange failed: {r.text}")
    return token


def is_authenticated(token: Optional[str]) -> bool:
    return bool(token)


def set_access_token(token: str) -> None:
    global _access_token
    _access_token = token


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def get_instruments() -> pd.DataFrame:
    r = requests.get(INSTRUMENTS_JSON_URL, timeout=60)
    r.raise_for_status()
    data = r.json()
    return pd.DataFrame(data)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def get_historical_candles(instrument_key: str, interval: str, start_date, end_date) -> pd.DataFrame:
    token = _require_token()
    # Map interval to v3 unit/granularity
    gran_map = {
        "1minute": ("minute", 1),
        "30minute": ("minute", 30),
        "day": ("day", 1),
        "week": ("week", 1),
        "month": ("month", 1),
    }
    unit, gran = gran_map.get(interval, ("day", 1))
    base = f"https://api.upstox.com/v3/historical-candle/{instrument_key}/{unit}/{gran}/{end_date.isoformat()}"
    if start_date:
        base = base + f"/{start_date.isoformat()}"

    headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
    resp = requests.get(base, headers=headers, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    candles = payload.get("data", {}).get("candles") or []

    cols = ["time", "open", "high", "low", "close", "volume", "oi"]
    df = pd.DataFrame(candles, columns=cols)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])  # contains tz info
        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


class _WSRunner:
    def __init__(self, instrument_key: str, on_message: Callable[[dict], None]):
        self.instrument_key = instrument_key
        self.on_message = on_message
        self._started = False
        self._streamer = None

    def _connect(self):
        token = _require_token()
        if upstox_client is None:
            raise RuntimeError("upstox-python-sdk not installed")
        configuration = upstox_client.Configuration()
        configuration.access_token = token
        streamer = upstox_client.MarketDataStreamerV3(
            upstox_client.ApiClient(configuration), [self.instrument_key], "ltp"
        )
        streamer.on("message", self.on_message)
        self._streamer = streamer
        streamer.connect()

    def start(self):
        if self._started:
            return
        self._started = True
        t = threading.Thread(target=self._connect, daemon=True)
        t.start()


_ws_cache: dict[str, _WSRunner] = {}


def stream_ltp(instrument_key: str, on_message: Callable[[dict], None]) -> _WSRunner:
    if instrument_key in _ws_cache:
        return _ws_cache[instrument_key]
    runner = _WSRunner(instrument_key, on_message)
    _ws_cache[instrument_key] = runner
    runner.start()
    return runner