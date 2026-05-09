from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame

from config import config


client = StockHistoricalDataClient(
    api_key=config.ALPACA_API_KEY,
    secret_key=config.ALPACA_SECRET_KEY,
)


def get_intraday_bars(ticker: str, minutes: int = 120) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=config.ALPACA_DATA_FEED,
    )

    bars = client.get_stock_bars(request).df

    if bars.empty:
        return pd.DataFrame()

    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(ticker, level=0)

    bars = bars.reset_index()
    bars.columns = [str(col).lower() for col in bars.columns]

    return bars


def get_latest_quote(ticker: str) -> dict:
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

    return {
        "bid": bid,
        "ask": ask,
        "spread": ask - bid if ask and bid else None,
        "mid": (ask + bid) / 2 if ask and bid else None,
    }
