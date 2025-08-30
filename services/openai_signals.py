import os
import json
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import BaseModel, Field
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()


class KeyLevels(BaseModel):
    support1: Optional[float] = None
    support2: Optional[float] = None
    resistance1: Optional[float] = None
    resistance2: Optional[float] = None
    pivot: Optional[float] = None


class Metric(BaseModel):
    name: str
    value: float | str
    unit: Optional[str] = None
    note: Optional[str] = None


class TradeSignal(BaseModel):
    direction: str = Field(description="buy/sell/hold")
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: float
    stop_loss: float
    take_profit: float
    rationale: str
    timeframe: str
    insights: Optional[str] = Field(default=None, description="Simple explanation for non-traders")
    risk_reward: Optional[float] = Field(default=None, description="Estimated RR ratio (>=1 is good)")
    key_levels: Optional[KeyLevels] = Field(default=None, description="Support/resistance levels")
    explanation_points: Optional[list[str]] = Field(default=None, description="Bullet points with plain-language reasons")
    metrics: Optional[list[Metric]] = Field(default=None, description="Key numeric metrics used in decision")
    expected_move_pct: Optional[float] = Field(default=None)
    stop_distance_pct: Optional[float] = Field(default=None)
    take_profit_distance_pct: Optional[float] = Field(default=None)
    caveats: Optional[list[str]] = Field(default=None)


def _format_candles_for_llm(df: pd.DataFrame) -> list[dict[str, Any]]:
    cols = ["time", "open", "high", "low", "close", "volume", "rsi", "sma_20", "sma_50", "macd", "macd_signal"]
    have = [c for c in cols if c in df.columns]
    return (
        df.tail(400)[have]
        .assign(time=lambda d: d["time"].astype(str))
        .to_dict(orient="records")
    )


def get_trade_signal(
    symbol: str,
    instrument_key: str,
    candles: pd.DataFrame,
    horizon: Optional[str] = None,
    analysis_interval: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    api_key = os.getenv("API_KEY_OPENAI")
    if not api_key:
        return {
            "error": "Missing API_KEY_OPENAI",
        }
    client = OpenAI(api_key=api_key)

    last = candles.iloc[-1]
    last_indicators: dict[str, Any] = {}
    for key in [
        "rsi", "sma_20", "sma_50", "ema_12", "ema_26",
        "macd", "macd_signal", "adx_14", "atr_14", "ema_200",
        "bb_upper", "bb_lower", "bb_mid",
    ]:
        if key in candles.columns and pd.notna(last.get(key)):
            last_indicators[key] = float(last.get(key))

    # Simple trend heuristic for context
    trend = "sideways"
    if all(k in candles.columns for k in ["sma_20", "sma_50", "ema_200"]):
        if last["sma_20"] > last["sma_50"] > last["ema_200"]:
            trend = "uptrend"
        elif last["sma_20"] < last["sma_50"] < last["ema_200"]:
            trend = "downtrend"
    last_indicators["trend"] = trend

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert quantitative trading assistant for Indian markets."
                " Use OHLC + indicators (RSI, EMA(12/26,200), SMA(20/50), MACD, ADX(14), ATR(14), Bollinger Bands)."
                " Evaluate trend, momentum, volatility, and support/resistance."
                " Provide risk-aware targets and stops with clear rationale that a non-trader can understand, with concrete numbers."
                " Be conservative unless multiple signals align."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Generate one trade idea for {symbol} ({instrument_key}). "
                f"Analysis interval: {analysis_interval or 'unspecified'}. "
                f"Analysis range: {from_date or 'auto'} to {to_date or 'auto'}. "
                f"Prediction horizon: {horizon or 'next session'} (e.g., next 30min, 1h, 1d, 1w). "
                "Focus on maximizing reward/risk and minimizing drawdown."
                " Return JSON only conforming to the provided schema."
                " Include: explanation_points (3-6 bullets, plain-language),"
                " metrics (key numbers like RSI value, MACD vs signal, ADX, ATR as % of price, BB %B),"
                " expected_move_pct, stop_distance_pct, take_profit_distance_pct, and any caveats."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "latest_close": float(candles["close"].iloc[-1]),
                "candles": _format_candles_for_llm(candles),
                "context": {
                    "horizon": horizon,
                    "analysis_interval": analysis_interval,
                    "from_date": from_date,
                    "to_date": to_date,
                    "last_indicators": last_indicators,
                },
            }),
        },
    ]

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=messages,
            response_format=TradeSignal,
        )

        msg = completion.choices[0].message
        parsed: TradeSignal = msg.parsed  # type: ignore
    except Exception as e:
        # Graceful fallback to avoid 500s
        last_close = float(candles["close"].iloc[-1])
        fallback = {
            "signal": "HOLD",
            "confidence": 0.2,
            "entry_price": last_close,
            "stop_loss": last_close * 0.98,
            "take_profit": last_close * 1.02,
            "timeframe": horizon or analysis_interval or "unspecified",
            "reasoning": f"AI temporarily unavailable: {str(e)}. Showing a conservative placeholder plan.",
            "insights": "Market context limited. Use caution.",
            "indicators": last_indicators,
            "explanation_points": [
                "No AI response; defaulting to tight risk management.",
                "Entry at last price; +/-2% bounds for risk and reward.",
            ],
            "metrics": [
                {"name": "RSI", "value": last_indicators.get("rsi", "n/a")},
                {"name": "ATR(14)", "value": last_indicators.get("atr_14", "n/a")},
            ],
            "caveats": ["This is a fallback, not a prediction."],
        }
        return fallback

    # Adapt to frontend shape and include indicator snapshot
    direction = (parsed.direction or "hold").strip().upper()
    if direction not in {"BUY", "SELL", "HOLD"}:
        direction = "HOLD"

    result: Dict[str, Any] = {
        "signal": direction,
        "confidence": float(parsed.confidence or 0.0),
        "entry_price": float(parsed.entry_price),
        "stop_loss": float(parsed.stop_loss),
        "take_profit": float(parsed.take_profit),
        "timeframe": parsed.timeframe or (horizon or "unspecified"),
        "reasoning": parsed.rationale,
        "insights": parsed.insights or parsed.rationale,
        "indicators": last_indicators,
    }
    # Optional extras if provided
    if parsed.risk_reward is not None:
        result["risk_reward"] = float(parsed.risk_reward)
    if parsed.key_levels is not None:
        result["key_levels"] = parsed.key_levels.dict()
    if parsed.explanation_points:
        result["explanation_points"] = parsed.explanation_points
    if parsed.metrics:
        result["metrics"] = [m.dict() for m in parsed.metrics]
    if parsed.expected_move_pct is not None:
        result["expected_move_pct"] = float(parsed.expected_move_pct)
    if parsed.stop_distance_pct is not None:
        result["stop_distance_pct"] = float(parsed.stop_distance_pct)
    if parsed.take_profit_distance_pct is not None:
        result["take_profit_distance_pct"] = float(parsed.take_profit_distance_pct)
    if parsed.caveats:
        result["caveats"] = parsed.caveats

    # Compute risk/reward if missing
    if "risk_reward" not in result:
        try:
            ep = result["entry_price"]
            sl = result["stop_loss"]
            tp = result["take_profit"]
            if direction == "BUY":
                rr = (tp - ep) / max(ep - sl, 1e-9)
            elif direction == "SELL":
                rr = (ep - tp) / max(sl - ep, 1e-9)
            else:
                rr = 0.0
            result["risk_reward"] = float(rr)
        except Exception:
            pass

    # Distances in percent if missing
    try:
        ep = result["entry_price"]
        if "stop_distance_pct" not in result:
            result["stop_distance_pct"] = float((abs(ep - result["stop_loss"]) / ep) * 100)
        if "take_profit_distance_pct" not in result:
            result["take_profit_distance_pct"] = float((abs(result["take_profit"] - ep) / ep) * 100)
    except Exception:
        pass

    return result
