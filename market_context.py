from indicators import get_indicator_snapshot


def get_market_context() -> dict:
    spy = get_indicator_snapshot("SPY")
    qqq = get_indicator_snapshot("QQQ")

    spy_momentum = spy.get("momentum_15m", 0)
    qqq_momentum = qqq.get("momentum_15m", 0)

    avg_momentum = (spy_momentum + qqq_momentum) / 2

    if avg_momentum > 0.003:
        regime = "bullish_intraday"
    elif avg_momentum < -0.003:
        regime = "bearish_intraday"
    elif abs(avg_momentum) < 0.001:
        regime = "chop"
    else:
        regime = "mixed"

    return {
        "regime": regime,
        "spy_momentum": spy_momentum,
        "qqq_momentum": qqq_momentum,
        "spy_above_vwap": spy.get("above_vwap"),
        "qqq_above_vwap": qqq.get("above_vwap"),
    }
