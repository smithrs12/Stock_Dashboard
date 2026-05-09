import math
from typing import Optional

from config import config
from market_data import get_intraday_bars, get_latest_quote


CORE_UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA",
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "AMD",
    "AVGO", "NFLX", "PLTR", "COIN", "MARA", "RIOT", "SMCI", "MU",
    "INTC", "TSM", "ARM", "CRM", "SHOP", "UBER", "LYFT", "DKNG",
    "SOFI", "AFRM", "ROKU", "SNAP", "RIVN", "LCID", "NIO", "F",
    "GME", "AMC", "CVNA", "BA", "JPM", "BAC", "XOM", "OXY",
]


def _pct(current: Optional[float], previous: Optional[float]) -> float:
    if current is None or previous in (None, 0):
        return 0.0
    return (current - previous) / previous


def _score_candidate(gap: float, momentum_5m: float, volume_ratio: float, dollar_volume: float) -> float:
    liquidity_score = math.log10(max(dollar_volume, 1)) / 10
    return (
        abs(gap) * 0.25
        + abs(momentum_5m) * 0.35
        + min(volume_ratio, 5.0) * 0.25
        + liquidity_score * 0.15
    )


def get_active_watchlist(limit: int = 30) -> list[str]:
    candidates = []

    for ticker in CORE_UNIVERSE:
        try:
            df = get_intraday_bars(ticker, minutes=45)
            if df.empty or len(df) < 10:
                continue

            latest = df.iloc[-1]
            first = df.iloc[0]
            prior_5 = df.iloc[-6:-1]

            price = float(latest["close"])
            if not (config.MIN_PRICE <= price <= config.MAX_PRICE):
                continue

            quote = get_latest_quote(ticker)
            spread = quote.get("spread")
            mid = quote.get("mid")

            if spread is not None and mid:
                spread_pct = spread / mid
                if spread_pct > 0.005:
                    continue

            gap = _pct(price, float(first["open"]))
            momentum_5m = _pct(price, float(prior_5.iloc[0]["open"]))

            avg_volume = float(prior_5["volume"].mean())
            latest_volume = float(latest["volume"])
            volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 0.0

            dollar_volume = float((df["close"] * df["volume"]).tail(10).sum())

            if dollar_volume < 1_000_000:
                continue

            score = _score_candidate(
                gap=gap,
                momentum_5m=momentum_5m,
                volume_ratio=volume_ratio,
                dollar_volume=dollar_volume,
            )

            candidates.append((ticker, score))

        except Exception:
            continue

    candidates.sort(key=lambda item: item[1], reverse=True)

    user_watchlist = config.WATCHLIST
    scanner_watchlist = [ticker for ticker, _ in candidates[:limit]]

    combined = []
    for ticker in user_watchlist + scanner_watchlist:
        if ticker not in combined:
            combined.append(ticker)

    return combined[:limit]
