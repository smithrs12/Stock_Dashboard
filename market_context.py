from indicators import get_indicator_snapshot


def _safe_avg(values: list[float]) -> float:
    valid = [value for value in values if value is not None]
    if not valid:
        return 0.0
    return sum(valid) / len(valid)


def _classify_volatility(spy: dict, qqq: dict) -> str:
    spy_atr_pct = spy.get("atr", 0) / spy.get("price", 1)
    qqq_atr_pct = qqq.get("atr", 0) / qqq.get("price", 1)

    avg_atr_pct = _safe_avg([spy_atr_pct, qqq_atr_pct])

    if avg_atr_pct >= 0.008:
        return "high_volatility"
    if avg_atr_pct >= 0.004:
        return "moderate_volatility"
    return "low_volatility"


def _classify_regime(
    avg_momentum_5m: float,
    avg_momentum_15m: float,
    avg_momentum_30m: float,
    market_above_vwap: bool,
    volatility_level: str,
) -> str:
    if volatility_level == "high_volatility" and abs(avg_momentum_15m) < 0.004:
        return "high_volatility_chop"

    if (
        avg_momentum_5m > 0.0015
        and avg_momentum_15m > 0.003
        and avg_momentum_30m > 0.004
        and market_above_vwap
    ):
        return "strong_trend_up"

    if avg_momentum_15m > 0.002 and market_above_vwap:
        return "weak_trend_up"

    if (
        avg_momentum_5m < -0.0015
        and avg_momentum_15m < -0.003
        and avg_momentum_30m < -0.004
        and not market_above_vwap
    ):
        return "strong_trend_down"

    if avg_momentum_15m < -0.002 and not market_above_vwap:
        return "weak_trend_down"

    if abs(avg_momentum_15m) < 0.0015:
        return "chop"

    return "mixed"


def get_market_context() -> dict:
    spy = get_indicator_snapshot("SPY")
    qqq = get_indicator_snapshot("QQQ")

    if not spy or not qqq:
        return {
            "regime": "unknown",
            "volatility_level": "unknown",
            "market_above_vwap": False,
            "spy_momentum_5m": 0.0,
            "spy_momentum_15m": 0.0,
            "spy_momentum_30m": 0.0,
            "qqq_momentum_5m": 0.0,
            "qqq_momentum_15m": 0.0,
            "qqq_momentum_30m": 0.0,
            "avg_momentum_5m": 0.0,
            "avg_momentum_15m": 0.0,
            "avg_momentum_30m": 0.0,
            "spy_above_vwap": False,
            "qqq_above_vwap": False,
        }

    spy_momentum_5m = spy.get("momentum_5m", 0.0)
    spy_momentum_15m = spy.get("momentum_15m", 0.0)
    spy_momentum_30m = spy.get("momentum_30m", 0.0)

    qqq_momentum_5m = qqq.get("momentum_5m", 0.0)
    qqq_momentum_15m = qqq.get("momentum_15m", 0.0)
    qqq_momentum_30m = qqq.get("momentum_30m", 0.0)

    avg_momentum_5m = _safe_avg([spy_momentum_5m, qqq_momentum_5m])
    avg_momentum_15m = _safe_avg([spy_momentum_15m, qqq_momentum_15m])
    avg_momentum_30m = _safe_avg([spy_momentum_30m, qqq_momentum_30m])

    spy_above_vwap = bool(spy.get("above_vwap", False))
    qqq_above_vwap = bool(qqq.get("above_vwap", False))

    market_above_vwap = spy_above_vwap and qqq_above_vwap

    volatility_level = _classify_volatility(spy, qqq)

    regime = _classify_regime(
        avg_momentum_5m=avg_momentum_5m,
        avg_momentum_15m=avg_momentum_15m,
        avg_momentum_30m=avg_momentum_30m,
        market_above_vwap=market_above_vwap,
        volatility_level=volatility_level,
    )

    risk_on_score = 0.0

    if spy_above_vwap:
        risk_on_score += 0.25
    if qqq_above_vwap:
        risk_on_score += 0.25
    if avg_momentum_15m > 0:
        risk_on_score += 0.25
    if avg_momentum_30m > 0:
        risk_on_score += 0.25

    return {
        "regime": regime,
        "volatility_level": volatility_level,
        "market_above_vwap": market_above_vwap,
        "risk_on_score": round(risk_on_score, 2),

        "spy_momentum_5m": round(spy_momentum_5m, 4),
        "spy_momentum_15m": round(spy_momentum_15m, 4),
        "spy_momentum_30m": round(spy_momentum_30m, 4),

        "qqq_momentum_5m": round(qqq_momentum_5m, 4),
        "qqq_momentum_15m": round(qqq_momentum_15m, 4),
        "qqq_momentum_30m": round(qqq_momentum_30m, 4),

        "avg_momentum_5m": round(avg_momentum_5m, 4),
        "avg_momentum_15m": round(avg_momentum_15m, 4),
        "avg_momentum_30m": round(avg_momentum_30m, 4),

        "spy_above_vwap": spy_above_vwap,
        "qqq_above_vwap": qqq_above_vwap,

        "spy_vwap_state": spy.get("vwap_state", "unknown"),
        "qqq_vwap_state": qqq.get("vwap_state", "unknown"),

        "spy_volume_ratio": round(spy.get("volume_ratio", 0.0), 2),
        "qqq_volume_ratio": round(qqq.get("volume_ratio", 0.0), 2),
    }
