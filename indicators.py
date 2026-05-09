import numpy as np
import pandas as pd

from market_data import get_intraday_bars


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    return (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()


def get_support_resistance(df: pd.DataFrame, lookback: int = 30) -> tuple:
    recent = df.tail(lookback)
    return float(recent["low"].min()), float(recent["high"].max())


def get_indicator_snapshot(ticker: str) -> dict:
    df = get_intraday_bars(ticker, minutes=180)

    if df.empty or len(df) < 30:
        return {}

    df["vwap"] = calculate_vwap(df)

    latest = df.iloc[-1]
    previous_15 = df.iloc[-15]

    price = float(latest["close"])
    vwap = float(latest["vwap"])

    rolling_volume = df["volume"].rolling(20).mean().iloc[-1]
    volume_ratio = float(latest["volume"] / rolling_volume) if rolling_volume else 0.0

    momentum_15m = (price - float(previous_15["close"])) / float(previous_15["close"])

    high_low = df["high"] - df["low"]
    atr = float(high_low.rolling(14).mean().iloc[-1])

    support, resistance = get_support_resistance(df)

    return {
        "ticker": ticker,
        "price": price,
        "vwap": vwap,
        "above_vwap": price > vwap,
        "vwap_distance": (price - vwap) / vwap if vwap else 0,
        "volume": float(latest["volume"]),
        "volume_ratio": volume_ratio,
        "momentum_15m": float(momentum_15m),
        "atr": atr,
        "support": support,
        "resistance": resistance,
        "day_high": float(df["high"].max()),
        "day_low": float(df["low"].min()),
    }
