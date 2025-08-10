import pandas as pd


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
    return out