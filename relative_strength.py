from indicators import get_indicator_snapshot


SECTOR_ETF_MAP = {
    "AAPL": "XLK",
    "MSFT": "XLK",
    "NVDA": "XLK",
    "AMD": "XLK",
    "AVGO": "XLK",
    "TSM": "XLK",
    "ARM": "XLK",
    "ANET": "XLK",
    "MRVL": "XLK",
    "DELL": "XLK",
    "ADBE": "XLK",
    "CRM": "XLK",
    "SNOW": "XLK",
    "PLTR": "XLK",
    "CRWD": "XLK",
    "PANW": "XLK",
    "DDOG": "XLK",

    "AMZN": "XLY",
    "TSLA": "XLY",
    "HD": "XLY",
    "LOW": "XLY",
    "MCD": "XLY",
    "NKE": "XLY",
    "SBUX": "XLY",
    "RIVN": "XLY",
    "LCID": "XLY",
    "F": "XLY",
    "GM": "XLY",
    "ROKU": "XLY",

    "META": "XLC",
    "GOOGL": "XLC",
    "NFLX": "XLC",
    "DIS": "XLC",
    "SNAP": "XLC",

    "JPM": "XLF",
    "BAC": "XLF",
    "GS": "XLF",
    "MS": "XLF",
    "WFC": "XLF",
    "C": "XLF",
    "SOFI": "XLF",
    "AFRM": "XLF",
    "HOOD": "XLF",
    "COIN": "XLF",

    "XOM": "XLE",
    "CVX": "XLE",
    "OXY": "XLE",
    "SLB": "XLE",

    "LLY": "XLV",
    "UNH": "XLV",
    "JNJ": "XLV",
    "PFE": "XLV",
    "MRK": "XLV",

    "WMT": "XLP",
    "COST": "XLP",
    "PG": "XLP",
    "KO": "XLP",
    "PEP": "XLP",

    "BA": "XLI",
    "CAT": "XLI",
    "GE": "XLI",
    "HON": "XLI",
    "RKLB": "XLI",

    "AMT": "XLRE",
    "PLD": "XLRE",

    "NEE": "XLU",
    "DUK": "XLU",

    "LIN": "XLB",
    "FCX": "XLB",

    "MARA": "IBIT",
    "RIOT": "IBIT",
}


DEFAULT_SECTOR_ETF = "SPY"


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_sector_etf(ticker: str) -> str:
    return SECTOR_ETF_MAP.get(ticker.upper(), DEFAULT_SECTOR_ETF)


def _classify_relationship(diff: float, strong_threshold: float = 0.003, mild_threshold: float = 0.001) -> str:
    if diff >= strong_threshold:
        return "strongly_outperforming"
    if diff >= mild_threshold:
        return "outperforming"
    if diff <= -strong_threshold:
        return "strongly_underperforming"
    if diff <= -mild_threshold:
        return "underperforming"
    return "in_line"


def _score_from_diff(diff: float) -> float:
    if diff >= 0.006:
        return 0.15
    if diff >= 0.003:
        return 0.10
    if diff >= 0.001:
        return 0.05
    if diff <= -0.006:
        return -0.15
    if diff <= -0.003:
        return -0.10
    if diff <= -0.001:
        return -0.05
    return 0.0


def get_relative_strength_snapshot(ticker: str) -> dict:
    ticker = ticker.upper()
    sector_etf = get_sector_etf(ticker)

    ticker_data = get_indicator_snapshot(ticker)
    spy_data = get_indicator_snapshot("SPY")
    qqq_data = get_indicator_snapshot("QQQ")
    sector_data = get_indicator_snapshot(sector_etf)

    if not ticker_data or not spy_data or not qqq_data or not sector_data:
        return {
            "ticker": ticker,
            "sector_etf": sector_etf,
            "rs_score": 0.0,
            "market_relative_label": "unknown",
            "qqq_relative_label": "unknown",
            "sector_relative_label": "unknown",
            "relative_strength_summary": "unknown",
        }

    ticker_momentum_5m = _safe_float(ticker_data.get("momentum_5m"))
    ticker_momentum_15m = _safe_float(ticker_data.get("momentum_15m"))
    ticker_momentum_30m = _safe_float(ticker_data.get("momentum_30m"))

    spy_momentum_5m = _safe_float(spy_data.get("momentum_5m"))
    spy_momentum_15m = _safe_float(spy_data.get("momentum_15m"))
    spy_momentum_30m = _safe_float(spy_data.get("momentum_30m"))

    qqq_momentum_5m = _safe_float(qqq_data.get("momentum_5m"))
    qqq_momentum_15m = _safe_float(qqq_data.get("momentum_15m"))
    qqq_momentum_30m = _safe_float(qqq_data.get("momentum_30m"))

    sector_momentum_5m = _safe_float(sector_data.get("momentum_5m"))
    sector_momentum_15m = _safe_float(sector_data.get("momentum_15m"))
    sector_momentum_30m = _safe_float(sector_data.get("momentum_30m"))

    rs_vs_spy_5m = ticker_momentum_5m - spy_momentum_5m
    rs_vs_spy_15m = ticker_momentum_15m - spy_momentum_15m
    rs_vs_spy_30m = ticker_momentum_30m - spy_momentum_30m

    rs_vs_qqq_5m = ticker_momentum_5m - qqq_momentum_5m
    rs_vs_qqq_15m = ticker_momentum_15m - qqq_momentum_15m
    rs_vs_qqq_30m = ticker_momentum_30m - qqq_momentum_30m

    rs_vs_sector_5m = ticker_momentum_5m - sector_momentum_5m
    rs_vs_sector_15m = ticker_momentum_15m - sector_momentum_15m
    rs_vs_sector_30m = ticker_momentum_30m - sector_momentum_30m

    weighted_market_rs = (
        rs_vs_spy_5m * 0.25 +
        rs_vs_spy_15m * 0.35 +
        rs_vs_spy_30m * 0.40
    )

    weighted_qqq_rs = (
        rs_vs_qqq_5m * 0.25 +
        rs_vs_qqq_15m * 0.35 +
        rs_vs_qqq_30m * 0.40
    )

    weighted_sector_rs = (
        rs_vs_sector_5m * 0.25 +
        rs_vs_sector_15m * 0.35 +
        rs_vs_sector_30m * 0.40
    )

    market_relative_label = _classify_relationship(weighted_market_rs)
    qqq_relative_label = _classify_relationship(weighted_qqq_rs)
    sector_relative_label = _classify_relationship(weighted_sector_rs)

    rs_score = (
        _score_from_diff(weighted_market_rs) +
        _score_from_diff(weighted_qqq_rs) +
        _score_from_diff(weighted_sector_rs)
    )

    if weighted_market_rs > 0.002 and weighted_sector_rs > 0.002:
        summary = "leading_market_and_sector"
    elif weighted_market_rs > 0.002:
        summary = "leading_market"
    elif weighted_sector_rs > 0.002:
        summary = "leading_sector"
    elif weighted_market_rs < -0.002 and weighted_sector_rs < -0.002:
        summary = "lagging_market_and_sector"
    elif weighted_market_rs < -0.002:
        summary = "lagging_market"
    elif weighted_sector_rs < -0.002:
        summary = "lagging_sector"
    else:
        summary = "mixed_relative_strength"

    return {
        "ticker": ticker,
        "sector_etf": sector_etf,
        "rs_score": round(rs_score, 4),

        "rs_vs_spy_5m": round(rs_vs_spy_5m, 4),
        "rs_vs_spy_15m": round(rs_vs_spy_15m, 4),
        "rs_vs_spy_30m": round(rs_vs_spy_30m, 4),

        "rs_vs_qqq_5m": round(rs_vs_qqq_5m, 4),
        "rs_vs_qqq_15m": round(rs_vs_qqq_15m, 4),
        "rs_vs_qqq_30m": round(rs_vs_qqq_30m, 4),

        "rs_vs_sector_5m": round(rs_vs_sector_5m, 4),
        "rs_vs_sector_15m": round(rs_vs_sector_15m, 4),
        "rs_vs_sector_30m": round(rs_vs_sector_30m, 4),

        "market_relative_label": market_relative_label,
        "qqq_relative_label": qqq_relative_label,
        "sector_relative_label": sector_relative_label,
        "relative_strength_summary": summary,
    }
