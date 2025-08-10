import os
import json
from typing import Any, Dict

import pandas as pd
from pydantic import BaseModel, Field
from openai import OpenAI


class TradeSignal(BaseModel):
    direction: str = Field(description="buy/sell/hold")
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: float
    stop_loss: float
    take_profit: float
    rationale: str
    timeframe: str


def _format_candles_for_llm(df: pd.DataFrame) -> list[dict[str, Any]]:
    cols = ["time", "open", "high", "low", "close", "volume", "rsi", "sma_20", "sma_50", "macd", "macd_signal"]
    have = [c for c in cols if c in df.columns]
    return (
        df.tail(400)[have]
        .assign(time=lambda d: d["time"].astype(str))
        .to_dict(orient="records")
    )


def get_trade_signal(symbol: str, instrument_key: str, candles: pd.DataFrame) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "error": "Missing OPENAI_API_KEY",
        }
    client = OpenAI(api_key=api_key)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert quantitative trading assistant for Indian markets."
                " You must produce high-precision entry/exit using recent OHLC with RSI, EMA, MACD."
                " Be conservative on confidence unless multiple signals align."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Generate one trade idea for {symbol} ({instrument_key}). "
                f"Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "latest_close": float(candles["close"].iloc[-1]),
                "candles": _format_candles_for_llm(candles),
            }),
        },
    ]

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=messages,
        response_format=TradeSignal,
    )

    msg = completion.choices[0].message
    parsed: TradeSignal = msg.parsed  # type: ignore
    return parsed.dict()