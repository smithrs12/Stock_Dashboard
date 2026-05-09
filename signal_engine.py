from datetime import datetime, timezone

from config import config
from indicators import get_indicator_snapshot
from market_context import get_market_context


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def generate_signal(ticker: str) -> dict:
    data = get_indicator_snapshot(ticker)
    if not data:
        return {}

    context = get_market_context()
    regime = context["regime"]

    score = 0.50
    reasons = []
    risks = []

    if data["momentum_15m"] > 0.004:
        score += 0.15
        reasons.append(f"Strong 15-minute momentum: {data['momentum_15m']:.2%}")
    elif data["momentum_15m"] < -0.004:
        score -= 0.15
        risks.append(f"Weak 15-minute momentum: {data['momentum_15m']:.2%}")

    if data["above_vwap"]:
        score += 0.15
        reasons.append(f"Price is above VWAP by {data['vwap_distance']:.2%}")
    else:
        score -= 0.12
        risks.append(f"Price is below VWAP by {abs(data['vwap_distance']):.2%}")

    if data["volume_ratio"] >= config.MIN_VOLUME_RATIO:
        score += 0.17
        reasons.append(f"Volume expansion: {data['volume_ratio']:.2f}x recent average")
    else:
        score -= 0.08
        risks.append(f"Volume is not strong enough: {data['volume_ratio']:.2f}x")

    if regime == "bullish_intraday":
        score += 0.08
        reasons.append("SPY/QQQ intraday context is supportive")
    elif regime == "bearish_intraday":
        score -= 0.10
        risks.append("SPY/QQQ intraday context is hostile")

    price = data["price"]
    atr = data["atr"]

    stop = max(data["support"], price - (1.5 * atr)) if atr else price * 0.98
    target = min(data["resistance"], price + (2.5 * atr)) if data["resistance"] > price else price * 1.04

    downside = abs(price - stop)
    upside = abs(target - price)
    risk_reward = upside / downside if downside else 0

    if risk_reward >= config.MIN_RISK_REWARD:
        score += 0.08
        reasons.append(f"Risk/reward acceptable: {risk_reward:.2f}")
    else:
        score -= 0.10
        risks.append(f"Risk/reward weak: {risk_reward:.2f}")

    confidence = clamp(score)

    if confidence >= config.SIGNAL_MIN_CONFIDENCE and data["above_vwap"] and data["momentum_15m"] > 0:
        signal = "BUY"
    elif confidence <= 0.40:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "ticker": ticker,
        "signal": signal,
        "confidence": round(confidence, 4),
        "price": round(price, 4),
        "entry_zone": round(price, 4) if signal == "BUY" else None,
        "stop": round(stop, 4),
        "target": round(target, 4),
        "risk_reward": round(risk_reward, 2),
        "regime": regime,
        "volume_ratio": round(data["volume_ratio"], 2),
        "momentum_15m": round(data["momentum_15m"], 4),
        "vwap_distance": round(data["vwap_distance"], 4),
        "reasons": reasons,
        "risks": risks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def generate_signals(tickers: list[str]) -> list[dict]:
    signals = []

    for ticker in tickers:
        signal = generate_signal(ticker)
        if signal:
            signals.append(signal)

    return sorted(signals, key=lambda item: item["confidence"], reverse=True)
