from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame

from config import config


client = StockHistoricalDataClient(
    api_key=config.ALPACA_API_KEY,
    secret_key=config.ALPACA_SECRET_KEY,
)


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trade_count",
            "vwap",
        ]
    )


def get_intraday_bars(ticker: str, minutes: int = 120) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    try:
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            feed=config.ALPACA_DATA_FEED,
        )

        bars = client.get_stock_bars(request).df

        if bars.empty:
            return _empty_bars()

        if isinstance(bars.index, pd.MultiIndex):
            try:
                bars = bars.xs(ticker, level=0)
            except KeyError:
                return _empty_bars()

        bars = bars.reset_index()
        bars.columns = [str(col).lower() for col in bars.columns]

        required_cols = ["open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in bars.columns:
                return _empty_bars()

        bars = bars.sort_values("timestamp").reset_index(drop=True)

        numeric_cols = ["open", "high", "low", "close", "volume", "trade_count", "vwap"]
        for col in numeric_cols:
            if col in bars.columns:
                bars[col] = pd.to_numeric(bars[col], errors="coerce")

        bars = bars.dropna(subset=["open", "high", "low", "close", "volume"])

        return bars

    except Exception as exc:
        print(f"[market_data] failed to fetch bars for {ticker}: {exc}")
        return _empty_bars()


def get_latest_quote(ticker: str) -> dict:
    try:
        request = StockLatestQuoteRequest(
            symbol_or_symbols=ticker,
            feed=config.ALPACA_DATA_FEED,
        )

        quotes = client.get_stock_latest_quote(request)
        quote = quotes.get(ticker)

        if not quote:
            return {}

        bid = float(quote.bid_price or 0)
        ask = float(quote.ask_price or 0)

        mid = (ask + bid) / 2 if ask and bid else None
        spread = ask - bid if ask and bid else None
        spread_pct = spread / mid if spread is not None and mid else None

        return {
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "spread_pct": spread_pct,
            "mid": mid,
        }

    except Exception as exc:
        print(f"[market_data] failed to fetch quote for {ticker}: {exc}")
        return {}


def get_latest_price(ticker: str) -> Optional[float]:
    bars = get_intraday_bars(ticker, minutes=10)

    if bars.empty:
        quote = get_latest_quote(ticker)
        return quote.get("mid")

    return float(bars.iloc[-1]["close"])


def is_liquid_quote(ticker: str, max_spread_pct: float = 0.005) -> bool:
    quote = get_latest_quote(ticker)

    spread_pct = quote.get("spread_pct")
    mid = quote.get("mid")

    if mid is None or spread_pct is None:
        return False

    return spread_pct <= max_spread_pct
