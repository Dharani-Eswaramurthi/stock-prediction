import json
import gzip
import io
import time
import threading
from typing import Callable, Optional

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_fixed
from urllib.parse import quote

from backend.config import UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI
import os

try:
    import upstox_client
except Exception:
    upstox_client = None  # type: ignore

UPSTOX_AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
INSTRUMENTS_JSON_URLS = [
    # Candidate endpoints; first item can be overridden by env
    os.getenv("INSTRUMENTS_URL") or "https://assets.upstox.com/market-quote/instruments/exchange/complete.json",
    "https://assets-v2.upstox.com/market-quote/instruments/exchange/complete.json",
    # Per-exchange fallbacks
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json",
    "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json",
    "https://assets.upstox.com/market-quote/instruments/exchange/MCX.json",
]

INSTRUMENTS_GZ_URLS = [
    os.getenv("INSTRUMENTS_GZ_URL") or "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
]

_complete_df_cache: Optional[pd.DataFrame] = None
_complete_df_cache_at: float = 0.0
_COMPLETE_CACHE_TTL_SECONDS = int(os.getenv("INSTRUMENTS_CACHE_TTL", "3600"))

_access_token: Optional[str] = None


def get_authorize_url() -> str:
    params = {
        "response_type": "code",
        "client_id": UPSTOX_CLIENT_ID,
        "redirect_uri": UPSTOX_REDIRECT_URI,
    }
    return f"{UPSTOX_AUTH_URL}?" + requests.compat.urlencode(params)


def exchange_code_for_token(code: str) -> str:
    data = {
        "code": code,
        "client_id": UPSTOX_CLIENT_ID,
        "client_secret": UPSTOX_CLIENT_SECRET,
        "redirect_uri": UPSTOX_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    headers = {"accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError(f"Token exchange failed: {r.text}")
    return token


def set_access_token(token: str) -> None:
    global _access_token
    _access_token = token


def is_authenticated() -> bool:
    return bool(_access_token)


def _curated_minimal_df() -> pd.DataFrame:
    # Minimal set for resiliency if remote instruments are blocked
    records = [
        {"segment": "NSE_INDEX", "trading_symbol": "Nifty 50", "instrument_key": "NSE_INDEX|Nifty 50", "instrument_type": "INDEX"},
        {"segment": "NSE_INDEX", "trading_symbol": "Nifty Bank", "instrument_key": "NSE_INDEX|Nifty Bank", "instrument_type": "INDEX"},
        {"segment": "NSE_EQ", "trading_symbol": "RELIANCE", "instrument_key": "NSE_EQ|INE002A01018", "instrument_type": "EQ"},
        {"segment": "NSE_EQ", "trading_symbol": "TCS", "instrument_key": "NSE_EQ|INE467B01029", "instrument_type": "EQ"},
        {"segment": "NSE_EQ", "trading_symbol": "INFY", "instrument_key": "NSE_EQ|INE009A01021", "instrument_type": "EQ"},
        {"segment": "NSE_EQ", "trading_symbol": "HDFCBANK", "instrument_key": "NSE_EQ|INE040A01034", "instrument_type": "EQ"},
        {"segment": "NSE_EQ", "trading_symbol": "ICICIBANK", "instrument_key": "NSE_EQ|INE090A01021", "instrument_type": "EQ"},
        {"segment": "NSE_EQ", "trading_symbol": "ITC", "instrument_key": "NSE_EQ|INE154A01025", "instrument_type": "EQ"},
        {"segment": "NSE_EQ", "trading_symbol": "SBIN", "instrument_key": "NSE_EQ|INE062A01020", "instrument_type": "EQ"},
    ]
    return pd.DataFrame(records)


def _sanitize_text(value: str) -> str:
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


@retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
def get_instruments(exchange: Optional[str] = None, query: Optional[str] = None, limit: int = 50) -> pd.DataFrame:
    def _load_complete_instruments() -> pd.DataFrame:
        global _complete_df_cache, _complete_df_cache_at
        now = time.time()
        if _complete_df_cache is not None and (now - _complete_df_cache_at) < _COMPLETE_CACHE_TTL_SECONDS:
            return _complete_df_cache
        # Try gzip first
        headers_gz = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"}
        for url in INSTRUMENTS_GZ_URLS:
            try:
                r = requests.get(url, headers=headers_gz, timeout=90)
                if r.status_code == 200 and r.content:
                    with gzip.GzipFile(fileobj=io.BytesIO(r.content)) as gz:
                        data_bytes = gz.read()
                    items = json.loads(data_bytes.decode("utf-8"))
                    df_local = pd.DataFrame(items)
                    if not df_local.empty:
                        _complete_df_cache = df_local
                        _complete_df_cache_at = now
                        return df_local
            except Exception:
                continue
        # Fallback to uncompressed
        headers = {"User-Agent": "Mozilla/5.0"}
        for url in INSTRUMENTS_JSON_URLS[:2]:
            try:
                r = requests.get(url, headers=headers, timeout=90)
                if r.status_code == 200:
                    df_local = pd.DataFrame(r.json())
                    if not df_local.empty:
                        _complete_df_cache = df_local
                        _complete_df_cache_at = now
                        return df_local
            except Exception:
                continue
        return pd.DataFrame()

    print("[DEBUG] Getting instruments", query)
    # Prefer local cache if provided to bypass remote 403s
    local_file = os.getenv("INSTRUMENTS_LOCAL_FILE")
    if local_file and os.path.exists(local_file):
        try:
            return pd.read_json(local_file)
        except Exception:
            pass

    headers = {"User-Agent": "Mozilla/5.0"}
    # If a query is provided, prefer using the complete list for best coverage
    if query:
        df = _load_complete_instruments()
        # Fallback to per-exchange if complete.json not available
        if df.empty:
            frames: list[pd.DataFrame] = []
            for url in INSTRUMENTS_JSON_URLS[2:]:
                try:
                    r = requests.get(url, headers=headers, timeout=60)
                    if r.status_code == 200:
                        data = r.json()
                        sub = pd.DataFrame(data)
                        if not sub.empty:
                            frames.append(sub)
                except Exception:
                    continue
            if frames:
                df = pd.concat(frames, ignore_index=True)

        if not df.empty:
            q = _sanitize_text(query)
            symbols = df.get("trading_symbol")
            names = df.get("name")
            symbols_s = symbols.astype(str).map(_sanitize_text) if symbols is not None else pd.Series([""] * len(df))
            names_s = names.astype(str).map(_sanitize_text) if names is not None else pd.Series([""] * len(df))
            mask = symbols_s.str.contains(q, na=False) | names_s.str.contains(q, na=False)
            filtered = df[mask].copy()
            if not filtered.empty:
                if "trading_symbol" in filtered.columns:
                    filtered.sort_values("trading_symbol", inplace=True)
                return filtered.head(limit)
        # If still empty, return minimal curated for UI resilience
        return _curated_minimal_df()

    if exchange:
        ex = exchange.strip().upper()
        url = f"https://assets.upstox.com/market-quote/instruments/exchange/{ex}.json"
        try:
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()
            data = r.json()
            df = pd.DataFrame(data)
            return df
        except Exception:
            # Fallback to complete list if single exchange fetch fails
            pass

    frames: list[pd.DataFrame] = []
    for url in INSTRUMENTS_JSON_URLS:
        if not url:
            continue
        try:
            r = requests.get(url, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                df = pd.DataFrame(data)
                if not df.empty:
                    frames.append(df)
        except Exception:
            continue
    if frames:
        df_all = pd.concat(frames, ignore_index=True)
        return df_all.head(limit) if limit else df_all
    # Fallback curated
    return _curated_minimal_df()


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def get_historical_candles(
    instrument_key: str,
    unit: str,
    interval: str,
    to_date: str,
    from_date: Optional[str],
) -> pd.DataFrame:
    if not _access_token:
        raise RuntimeError("Not authenticated")
    # Encode instrument key for safe path usage
    safe_instrument_key = quote(instrument_key, safe="")
    base = (
        f"https://api.upstox.com/v3/historical-candle/"
        f"{safe_instrument_key}/{unit}/{interval}/{to_date}"
    )
    if from_date:
        base = base + f"/{from_date}"
    headers = {"Authorization": f"Bearer {_access_token}", "accept": "application/json"}
    print("[DEBUG] access token", _access_token)
    # Debug: request context for diagnostics
    print("[DEBUG] Historical candles url:", base)
    resp = requests.get(base, headers=headers, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    candles = payload.get("data", {}).get("candles") or []
    cols = ["time", "open", "high", "low", "close", "volume", "oi"]
    df = pd.DataFrame(candles, columns=cols)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])  # keep tz
        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


class _WSRunner:
    def __init__(self, instrument_key: str, on_message: Callable[[dict], None]):
        self.instrument_key = instrument_key
        self.on_message = on_message
        self._streamer = None

    def _connect(self):
        if not _access_token:
            raise RuntimeError("Not authenticated")
        if upstox_client is None:
            raise RuntimeError("upstox-python-sdk not installed")
        configuration = upstox_client.Configuration()
        configuration.access_token = _access_token
        streamer = upstox_client.MarketDataStreamerV3(
            upstox_client.ApiClient(configuration), [self.instrument_key], "ltp"
        )
        streamer.on("message", self.on_message)
        self._streamer = streamer
        streamer.connect()

    def start(self):
        t = threading.Thread(target=self._connect, daemon=True)
        t.start()


_ws_cache: dict[str, _WSRunner] = {}


def get_stream_runner(instrument_key: str, on_message: Callable[[dict], None]) -> _WSRunner:
    if instrument_key in _ws_cache:
        return _ws_cache[instrument_key]
    r = _WSRunner(instrument_key, on_message)
    _ws_cache[instrument_key] = r
    r.start()
    return r