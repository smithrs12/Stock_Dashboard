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
    "PANW", "CRWD", "ADBE", "MRVL", "ANET", "SNOW", "DDOG", "CELH",
    "APP", "HOOD", "HIMS", "RKLB", "CLS", "DELL", "WMT", "COST",
]


def _pct(current: Optional[float], previous: Optional[float]) -> float:
    if current is None or previous in (None, 0):
        return 0.0
    return (current - previous) / previous


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_candidate(
    gap_from_open: float,
    momentum_5m: float,
    momentum_15m: float,
    volume_ratio: float,
    dollar_volume: float,
    near_high_score: float,
) -> float:
    liquidity_score = min(math.log10(max(dollar_volume, 1)) / 10, 1.0)

    return (
        abs(gap_from_open) * 0.18
        + abs(momentum_5m) * 0.22
        + abs(momentum_15m) * 0.24
        + min(volume_ratio, 5.0) * 0.22
        + near_high_score * 0.04
        + liquidity_score * 0.10
    )


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    output = []

    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)

    return output


def get_scanner_candidates(limit: int | None = None) -> list[dict]:
    if limit is None:
        limit = config.WATCHLIST_LIMIT

    candidates = []

    for ticker in CORE_UNIVERSE:
        try:
            df = get_intraday_bars(ticker, minutes=90)
            if df.empty or len(df) < 20:
                continue

            latest = df.iloc[-1]
            open_bar = df.iloc[0]
            prev_5 = df.iloc[-6]
            prev_15 = df.iloc[-16]

            price = _safe_float(latest["close"])
            if not (config.MIN_PRICE <= price <= config.MAX_PRICE):
                continue

            quote = get_latest_quote(ticker)
            spread_pct = quote.get("spread_pct")

            if spread_pct is not None and spread_pct > config.MAX_SPREAD_PCT:
                continue

            rolling_volume = _safe_float(df["volume"].rolling(20).mean().iloc[-1])
            latest_volume = _safe_float(latest["volume"])
            volume_ratio = latest_volume / rolling_volume if rolling_volume > 0 else 0.0

            if volume_ratio < 0.8:
                continue

            gap_from_open = _pct(price, _safe_float(open_bar["open"]))
            momentum_5m = _pct(price, _safe_float(prev_5["close"]))
            momentum_15m = _pct(price, _safe_float(prev_15["close"]))

            dollar_volume = _safe_float((df["close"] * df["volume"]).tail(20).sum())
            if dollar_volume < 1_000_000:
                continue

            day_high = _safe_float(df["high"].max())
            near_high_score = 0.0
            if day_high > 0:
                near_high_score = max(0.0, 1.0 - abs((day_high - price) / day_high))

            score = _score_candidate(
                gap_from_open=gap_from_open,
                momentum_5m=momentum_5m,
                momentum_15m=momentum_15m,
                volume_ratio=volume_ratio,
                dollar_volume=dollar_volume,
                near_high_score=near_high_score,
            )

            candidates.append(
                {
                    "ticker": ticker,
                    "score": round(score, 4),
                    "price": round(price, 4),
                    "gap_from_open": round(gap_from_open, 4),
                    "momentum_5m": round(momentum_5m, 4),
                    "momentum_15m": round(momentum_15m, 4),
                    "volume_ratio": round(volume_ratio, 2),
                    "dollar_volume": round(dollar_volume, 2),
                    "spread_pct": round(spread_pct, 4) if spread_pct is not None else None,
                }
            )

        except Exception:
            continue

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


def get_active_watchlist(limit: int | None = None) -> list[str]:
    if limit is None:
        limit = config.WATCHLIST_LIMIT

    scanner_candidates = get_scanner_candidates(limit=limit)
    scanner_watchlist = [item["ticker"] for item in scanner_candidates]

    combined = _dedupe_preserve_order(config.WATCHLIST + scanner_watchlist)
    return combined[:limit]
