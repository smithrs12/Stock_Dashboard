from datetime import datetime, timezone

from config import config
from indicators import get_indicator_snapshot
from market_context import get_market_context


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def build_risk_plan(data: dict, signal: str) -> dict:
    price = data["price"]
    atr = data.get("atr", 0.0)
    support = data.get("support", price * 0.98)
    resistance = data.get("resistance", price * 1.04)

    if signal == "BUY":
        stop = max(support, price - (1.5 * atr)) if atr else price * 0.98
        target = min(resistance, price + (2.5 * atr)) if resistance > price else price * 1.04
    elif signal == "SELL":
        stop = min(resistance, price + (1.5 * atr)) if atr else price * 1.02
        target = max(support, price - (2.5 * atr)) if support < price else price * 0.96
    else:
        stop = None
        target = None

    if not stop or not target:
        return {
            "entry_zone": None,
            "stop": None,
            "target": None,
            "risk_reward": 0.0,
        }

    downside = abs(price - stop)
    upside = abs(target - price)
    risk_reward = upside / downside if downside else 0.0

    return {
        "entry_zone": round(price, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "risk_reward": round(risk_reward, 2),
    }


def score_long_setup(data: dict, regime: str) -> tuple[float, list[str], list[str], dict]:
    score = 0.50
    reasons = []
    risks = []

    breakdown = {
        "momentum": 0.0,
        "vwap": 0.0,
        "volume": 0.0,
        "trend": 0.0,
        "context": 0.0,
        "risk_reward": 0.0,
        "decay": 0.0,
    }

    if data["momentum_5m"] > 0.002 and data["momentum_15m"] > 0.004:
        score += 0.14
        breakdown["momentum"] += 0.14
        reasons.append(
            f"Momentum confirmed across 5m and 15m: "
            f"{data['momentum_5m']:.2%} / {data['momentum_15m']:.2%}"
        )
    elif data["momentum_15m"] > 0.004:
        score += 0.08
        breakdown["momentum"] += 0.08
        reasons.append(f"Positive 15-minute momentum: {data['momentum_15m']:.2%}")
    elif data["momentum_15m"] < -0.004:
        score -= 0.12
        breakdown["momentum"] -= 0.12
        risks.append(f"Negative 15-minute momentum: {data['momentum_15m']:.2%}")

    if data["momentum_acceleration"] > 0:
        score += 0.08
        breakdown["momentum"] += 0.08
        reasons.append(f"Momentum is accelerating: {data['momentum_acceleration']:.2%}")
    else:
        score -= 0.04
        breakdown["momentum"] -= 0.04
        risks.append(f"Momentum is decelerating: {data['momentum_acceleration']:.2%}")

    vwap_state = data.get("vwap_state", "neutral")

    if vwap_state == "reclaim":
        score += 0.15
        breakdown["vwap"] += 0.15
        reasons.append("VWAP reclaim detected")
    elif vwap_state == "above":
        score += 0.10
        breakdown["vwap"] += 0.10
        reasons.append(f"Price is above VWAP by {data['vwap_distance']:.2%}")
    elif vwap_state == "breakdown":
        score -= 0.16
        breakdown["vwap"] -= 0.16
        risks.append("VWAP breakdown detected")
    else:
        score -= 0.10
        breakdown["vwap"] -= 0.10
        risks.append(f"Price is below VWAP by {abs(data['vwap_distance']):.2%}")

    if data["volume_ratio"] >= 2.0:
        score += 0.16
        breakdown["volume"] += 0.16
        reasons.append(f"Strong volume expansion: {data['volume_ratio']:.2f}x recent average")
    elif data["volume_ratio"] >= config.MIN_VOLUME_RATIO:
        score += 0.10
        breakdown["volume"] += 0.10
        reasons.append(f"Volume expansion: {data['volume_ratio']:.2f}x recent average")
    else:
        score -= 0.08
        breakdown["volume"] -= 0.08
        risks.append(f"Volume is not strong enough: {data['volume_ratio']:.2f}x")

    if data.get("macd_histogram_rising"):
        score += 0.07
        breakdown["trend"] += 0.07
        reasons.append("MACD histogram is rising")
    else:
        score -= 0.04
        breakdown["trend"] -= 0.04
        risks.append("MACD histogram is not rising")

    if data.get("adx", 0) >= 18:
        score += 0.06
        breakdown["trend"] += 0.06
        reasons.append(f"Trend strength acceptable: ADX {data['adx']:.1f}")
    else:
        score -= 0.04
        breakdown["trend"] -= 0.04
        risks.append(f"Weak trend strength: ADX {data['adx']:.1f}")

    rsi = data.get("rsi", 50)

    if 45 <= rsi <= 72:
        score += 0.05
        breakdown["trend"] += 0.05
        reasons.append(f"RSI is constructive: {rsi:.1f}")
    elif rsi > 80:
        score -= 0.08
        breakdown["trend"] -= 0.08
        risks.append(f"RSI is extended: {rsi:.1f}")
    elif rsi < 35:
        score -= 0.06
        breakdown["trend"] -= 0.06
        risks.append(f"RSI is weak: {rsi:.1f}")

    distance_to_resistance = data.get("distance_to_resistance", 0.0)

    if distance_to_resistance >= 0.01:
        score += 0.05
        breakdown["risk_reward"] += 0.05
        reasons.append(f"Room to resistance: {distance_to_resistance:.2%}")
    else:
        score -= 0.07
        breakdown["risk_reward"] -= 0.07
        risks.append(f"Resistance is close overhead: {distance_to_resistance:.2%}")

    if regime in {"bullish_intraday", "trending", "mixed"}:
        score += 0.06
        breakdown["context"] += 0.06
        reasons.append(f"Market context is acceptable: {regime}")
    elif regime == "bearish_intraday":
        score -= 0.10
        breakdown["context"] -= 0.10
        risks.append("SPY/QQQ intraday context is bearish")
    elif regime == "chop":
        score -= 0.06
        breakdown["context"] -= 0.06
        risks.append("Market is choppy")

    if data.get("signal_decay"):
        score -= 0.14
        breakdown["decay"] -= 0.14
        risks.append("Signal decay detected: momentum, volume, or MACD is fading")

    return score, reasons, risks, breakdown


def score_short_setup(data: dict, regime: str) -> tuple[float, list[str], list[str], dict]:
    score = 0.50
    reasons = []
    risks = []

    breakdown = {
        "momentum": 0.0,
        "vwap": 0.0,
        "volume": 0.0,
        "trend": 0.0,
        "context": 0.0,
        "risk_reward": 0.0,
        "decay": 0.0,
    }

    if data["momentum_5m"] < -0.002 and data["momentum_15m"] < -0.004:
        score += 0.14
        breakdown["momentum"] += 0.14
        reasons.append(
            f"Downside momentum confirmed across 5m and 15m: "
            f"{data['momentum_5m']:.2%} / {data['momentum_15m']:.2%}"
        )
    elif data["momentum_15m"] < -0.004:
        score += 0.08
        breakdown["momentum"] += 0.08
        reasons.append(f"Negative 15-minute momentum: {data['momentum_15m']:.2%}")
    elif data["momentum_15m"] > 0.004:
        score -= 0.12
        breakdown["momentum"] -= 0.12
        risks.append(f"Upside momentum working against short: {data['momentum_15m']:.2%}")

    if data["momentum_acceleration"] < 0:
        score += 0.08
        breakdown["momentum"] += 0.08
        reasons.append(f"Downside momentum is accelerating: {data['momentum_acceleration']:.2%}")
    else:
        score -= 0.04
        breakdown["momentum"] -= 0.04
        risks.append(f"Downside momentum is not accelerating: {data['momentum_acceleration']:.2%}")

    vwap_state = data.get("vwap_state", "neutral")

    if vwap_state == "breakdown":
        score += 0.15
        breakdown["vwap"] += 0.15
        reasons.append("VWAP breakdown detected")
    elif vwap_state == "below":
        score += 0.10
        breakdown["vwap"] += 0.10
        reasons.append(f"Price is below VWAP by {abs(data['vwap_distance']):.2%}")
    elif vwap_state == "reclaim":
        score -= 0.16
        breakdown["vwap"] -= 0.16
        risks.append("VWAP reclaim detected against short")
    else:
        score -= 0.10
        breakdown["vwap"] -= 0.10
        risks.append(f"Price is above VWAP by {data['vwap_distance']:.2%}")

    if data["volume_ratio"] >= 2.0:
        score += 0.14
        breakdown["volume"] += 0.14
        reasons.append(f"Strong sell-side participation: {data['volume_ratio']:.2f}x volume")
    elif data["volume_ratio"] >= config.MIN_VOLUME_RATIO:
        score += 0.09
        breakdown["volume"] += 0.09
        reasons.append(f"Volume expansion: {data['volume_ratio']:.2f}x recent average")
    else:
        score -= 0.08
        breakdown["volume"] -= 0.08
        risks.append(f"Volume is not strong enough: {data['volume_ratio']:.2f}x")

    if not data.get("macd_histogram_rising"):
        score += 0.07
        breakdown["trend"] += 0.07
        reasons.append("MACD histogram is weakening")
    else:
        score -= 0.04
        breakdown["trend"] -= 0.04
        risks.append("MACD histogram is rising against short")

    if data.get("adx", 0) >= 18:
        score += 0.05
        breakdown["trend"] += 0.05
        reasons.append(f"Trend strength acceptable: ADX {data['adx']:.1f}")

    rsi = data.get("rsi", 50)

    if 28 <= rsi <= 55:
        score += 0.05
        breakdown["trend"] += 0.05
        reasons.append(f"RSI supports downside continuation: {rsi:.1f}")
    elif rsi < 25:
        score -= 0.08
        breakdown["trend"] -= 0.08
        risks.append(f"RSI is deeply oversold: {rsi:.1f}")

    distance_to_support = data.get("distance_to_support", 0.0)

    if distance_to_support >= 0.01:
        score += 0.05
        breakdown["risk_reward"] += 0.05
        reasons.append(f"Room to support: {distance_to_support:.2%}")
    else:
        score -= 0.07
        breakdown["risk_reward"] -= 0.07
        risks.append(f"Support is close below: {distance_to_support:.2%}")

    if regime == "bearish_intraday":
        score += 0.07
        breakdown["context"] += 0.07
        reasons.append("SPY/QQQ intraday context supports short")
    elif regime == "bullish_intraday":
        score -= 0.10
        breakdown["context"] -= 0.10
        risks.append("SPY/QQQ intraday context is bullish against short")
    elif regime == "chop":
        score -= 0.05
        breakdown["context"] -= 0.05
        risks.append("Market is choppy")

    return score, reasons, risks, breakdown


def choose_direction(long_score: float, short_score: float) -> str:
    if long_score >= config.SIGNAL_MIN_CONFIDENCE and long_score >= short_score + 0.08:
        return "BUY"

    if short_score >= config.SIGNAL_MIN_CONFIDENCE and short_score >= long_score + 0.08:
        return "SELL"

    return "HOLD"


def generate_signal(ticker: str, context: dict | None = None) -> dict:
    data = get_indicator_snapshot(ticker)
    if not data:
        return {}

    if context is None:
        context = get_market_context()

    regime = context.get("regime", "unknown")

    long_score, long_reasons, long_risks, long_breakdown = score_long_setup(data, regime)
    short_score, short_reasons, short_risks, short_breakdown = score_short_setup(data, regime)

    long_confidence = clamp(long_score)
    short_confidence = clamp(short_score)

    signal = choose_direction(long_confidence, short_confidence)

    if signal == "BUY":
        confidence = long_confidence
        reasons = long_reasons
        risks = long_risks + [f"Short setup confidence only {short_confidence:.2f}"]
        breakdown = long_breakdown
    elif signal == "SELL":
        confidence = short_confidence
        reasons = short_reasons
        risks = short_risks + [f"Long setup confidence only {long_confidence:.2f}"]
        breakdown = short_breakdown
    else:
        confidence = max(long_confidence, short_confidence)
        reasons = ["No clean directional edge"]
        risks = long_risks[:3] + short_risks[:3]
        breakdown = {
            "long_confidence": round(long_confidence, 4),
            "short_confidence": round(short_confidence, 4),
        }

    risk_plan = build_risk_plan(data, signal)

    if signal in {"BUY", "SELL"} and risk_plan["risk_reward"] < config.MIN_RISK_REWARD:
        risks.append(f"Blocked by weak risk/reward: {risk_plan['risk_reward']:.2f}")
        signal = "HOLD"
        confidence = min(confidence, 0.62)

    return {
        "ticker": ticker,
        "signal": signal,
        "confidence": round(confidence, 4),
        "long_confidence": round(long_confidence, 4),
        "short_confidence": round(short_confidence, 4),

        "price": round(data["price"], 4),
        "entry_zone": risk_plan["entry_zone"] if signal in {"BUY", "SELL"} else None,
        "stop": risk_plan["stop"] if signal in {"BUY", "SELL"} else None,
        "target": risk_plan["target"] if signal in {"BUY", "SELL"} else None,
        "risk_reward": risk_plan["risk_reward"] if signal in {"BUY", "SELL"} else 0.0,

        "regime": regime,
        "volume_ratio": round(data["volume_ratio"], 2),
        "volume_ratio_60": round(data["volume_ratio_60"], 2),
        "momentum_5m": round(data["momentum_5m"], 4),
        "momentum_15m": round(data["momentum_15m"], 4),
        "momentum_30m": round(data["momentum_30m"], 4),
        "momentum_acceleration": round(data["momentum_acceleration"], 4),
        "vwap_distance": round(data["vwap_distance"], 4),
        "vwap_state": data["vwap_state"],
        "rsi": round(data["rsi"], 2),
        "adx": round(data["adx"], 2),
        "macd_histogram": round(data["macd_histogram"], 4),
        "macd_histogram_rising": data["macd_histogram_rising"],
        "distance_to_support": round(data["distance_to_support"], 4),
        "distance_to_resistance": round(data["distance_to_resistance"], 4),
        "signal_decay": data["signal_decay"],

        "breakdown": breakdown,
        "reasons": reasons,
        "risks": risks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def generate_signals(tickers: list[str]) -> list[dict]:
    context = get_market_context()
    signals = []

    for ticker in tickers:
        signal = generate_signal(ticker, context=context)
        if signal:
            signals.append(signal)

    return sorted(signals, key=lambda item: item["confidence"], reverse=True)
