import pandas as pd
import numpy as np


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / (loss + 1e-12)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["sma_20"] = out["close"].rolling(20).mean()
    out["sma_50"] = out["close"].rolling(50).mean()
    out["ema_12"] = _ema(out["close"], 12)
    out["ema_26"] = _ema(out["close"], 26)
    out["rsi"] = _rsi(out["close"], 14)
    out["macd"] = out["ema_12"] - out["ema_26"]
    out["macd_signal"] = _ema(out["macd"], 9)
    # Bollinger Bands (20, 2)
    rolling_mean = out["close"].rolling(20).mean()
    rolling_std = out["close"].rolling(20).std()
    out["bb_mid"] = rolling_mean
    out["bb_upper"] = rolling_mean + 2 * rolling_std
    out["bb_lower"] = rolling_mean - 2 * rolling_std

    # True Range and ATR(14)
    prev_close = out["close"].shift(1)
    high_low = (out["high"] - out["low"]).abs()
    high_pc = (out["high"] - prev_close).abs()
    low_pc = (out["low"] - prev_close).abs()
    tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
    out["atr_14"] = tr.rolling(14).mean()

    # ADX(14)
    high_shift = out["high"].shift(1)
    low_shift = out["low"].shift(1)
    plus_dm = (out["high"] - high_shift)
    minus_dm = (low_shift - out["low"])
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    atr = out["atr_14"]
    # Avoid division by zero
    plus_di = 100 * (plus_dm.rolling(14).mean() / (atr.replace(0, np.nan)))
    minus_di = 100 * (minus_dm.rolling(14).mean() / (atr.replace(0, np.nan)))
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    out["adx_14"] = dx.rolling(14).mean()

    # Long trend EMA for context
    out["ema_200"] = _ema(out["close"], 200)
    return out
