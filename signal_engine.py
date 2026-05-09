from datetime import datetime, timezone

from config import config
from indicators import get_indicator_snapshot
from market_context import get_market_context
from market_data import get_latest_quote
from relative_strength import get_relative_strength_snapshot
from sentiment_engine import get_sentiment_snapshot


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


def apply_long_market_context(score: float, regime: str, breakdown: dict, reasons: list, risks: list) -> float:
    if regime == "strong_trend_up":
        score += 0.10
        breakdown["context"] += 0.10
        reasons.append("Market regime strongly supports long setups")
    elif regime == "weak_trend_up":
        score += 0.06
        breakdown["context"] += 0.06
        reasons.append("Market regime mildly supports long setups")
    elif regime == "mixed":
        score += 0.02
        breakdown["context"] += 0.02
        reasons.append("Market regime is mixed but acceptable")
    elif regime == "chop":
        score -= 0.07
        breakdown["context"] -= 0.07
        risks.append("Market is choppy")
    elif regime == "high_volatility_chop":
        score -= 0.12
        breakdown["context"] -= 0.12
        risks.append("High-volatility chop is hostile for clean long entries")
    elif regime == "weak_trend_down":
        score -= 0.10
        breakdown["context"] -= 0.10
        risks.append("Market regime is weak bearish against long setup")
    elif regime == "strong_trend_down":
        score -= 0.16
        breakdown["context"] -= 0.16
        risks.append("Market regime strongly opposes long setup")
    else:
        score -= 0.03
        breakdown["context"] -= 0.03
        risks.append(f"Market regime is unclear: {regime}")

    return score


def apply_short_market_context(score: float, regime: str, breakdown: dict, reasons: list, risks: list) -> float:
    if regime == "strong_trend_down":
        score += 0.10
        breakdown["context"] += 0.10
        reasons.append("Market regime strongly supports short setups")
    elif regime == "weak_trend_down":
        score += 0.06
        breakdown["context"] += 0.06
        reasons.append("Market regime mildly supports short setups")
    elif regime == "mixed":
        score += 0.01
        breakdown["context"] += 0.01
        reasons.append("Market regime is mixed but short is still possible")
    elif regime == "chop":
        score -= 0.06
        breakdown["context"] -= 0.06
        risks.append("Market is choppy")
    elif regime == "high_volatility_chop":
        score -= 0.10
        breakdown["context"] -= 0.10
        risks.append("High-volatility chop increases short-squeeze/reversal risk")
    elif regime == "weak_trend_up":
        score -= 0.10
        breakdown["context"] -= 0.10
        risks.append("Market regime is weak bullish against short setup")
    elif regime == "strong_trend_up":
        score -= 0.16
        breakdown["context"] -= 0.16
        risks.append("Market regime strongly opposes short setup")
    else:
        score -= 0.03
        breakdown["context"] -= 0.03
        risks.append(f"Market regime is unclear: {regime}")

    return score


def apply_sentiment_to_long(score: float, sentiment: dict, breakdown: dict, reasons: list, risks: list) -> float:
    sentiment_score = float(sentiment.get("sentiment_score", 0.0))
    mention_spike = bool(sentiment.get("mention_spike", False))
    top_catalyst = sentiment.get("top_catalyst")
    article_count = int(sentiment.get("article_count", 0))

    if sentiment_score >= 0.35:
        score += 0.10
        breakdown["sentiment"] += 0.10
        reasons.append(f"Bullish news sentiment: {sentiment_score:.2f}")
    elif sentiment_score >= 0.15:
        score += 0.05
        breakdown["sentiment"] += 0.05
        reasons.append(f"Positive news sentiment: {sentiment_score:.2f}")
    elif sentiment_score <= -0.35:
        score -= 0.12
        breakdown["sentiment"] -= 0.12
        risks.append(f"Bearish news sentiment: {sentiment_score:.2f}")
    elif sentiment_score <= -0.15:
        score -= 0.06
        breakdown["sentiment"] -= 0.06
        risks.append(f"Negative news sentiment: {sentiment_score:.2f}")

    if mention_spike and sentiment_score >= 0:
        score += 0.05
        breakdown["sentiment"] += 0.05
        reasons.append("News attention spike detected")
    elif mention_spike and sentiment_score < 0:
        score -= 0.04
        breakdown["sentiment"] -= 0.04
        risks.append("Negative attention spike detected")

    if article_count >= 3 and top_catalyst:
        score += 0.03
        breakdown["sentiment"] += 0.03
        reasons.append(f"Active catalyst flow detected: {top_catalyst}")

    if top_catalyst in {"offering", "legal"}:
        score -= 0.10
        breakdown["sentiment"] -= 0.10
        risks.append(f"Hostile catalyst for longs: {top_catalyst}")
    elif top_catalyst in {"earnings", "analyst", "contract", "fda", "mna"} and sentiment_score >= 0:
        score += 0.04
        breakdown["sentiment"] += 0.04
        reasons.append(f"Constructive catalyst for longs: {top_catalyst}")

    return score


def apply_sentiment_to_short(score: float, sentiment: dict, breakdown: dict, reasons: list, risks: list) -> float:
    sentiment_score = float(sentiment.get("sentiment_score", 0.0))
    mention_spike = bool(sentiment.get("mention_spike", False))
    top_catalyst = sentiment.get("top_catalyst")
    article_count = int(sentiment.get("article_count", 0))

    if sentiment_score <= -0.35:
        score += 0.10
        breakdown["sentiment"] += 0.10
        reasons.append(f"Bearish news sentiment: {sentiment_score:.2f}")
    elif sentiment_score <= -0.15:
        score += 0.05
        breakdown["sentiment"] += 0.05
        reasons.append(f"Negative news sentiment: {sentiment_score:.2f}")
    elif sentiment_score >= 0.35:
        score -= 0.12
        breakdown["sentiment"] -= 0.12
        risks.append(f"Bullish news sentiment against short: {sentiment_score:.2f}")
    elif sentiment_score >= 0.15:
        score -= 0.06
        breakdown["sentiment"] -= 0.06
        risks.append(f"Positive news sentiment against short: {sentiment_score:.2f}")

    if mention_spike and sentiment_score <= 0:
        score += 0.05
        breakdown["sentiment"] += 0.05
        reasons.append("Negative news attention spike detected")
    elif mention_spike and sentiment_score > 0:
        score -= 0.04
        breakdown["sentiment"] -= 0.04
        risks.append("Positive attention spike detected against short")

    if article_count >= 3 and top_catalyst:
        score += 0.03
        breakdown["sentiment"] += 0.03
        reasons.append(f"Active catalyst flow detected: {top_catalyst}")

    if top_catalyst in {"offering", "legal"} and sentiment_score <= 0:
        score += 0.07
        breakdown["sentiment"] += 0.07
        reasons.append(f"Constructive catalyst for shorts: {top_catalyst}")
    elif top_catalyst in {"earnings", "analyst", "contract", "fda", "mna"} and sentiment_score > 0:
        score -= 0.05
        breakdown["sentiment"] -= 0.05
        risks.append(f"Bullish catalyst against short: {top_catalyst}")

    return score


def apply_liquidity_checks(score: float, quote: dict, breakdown: dict, reasons: list, risks: list) -> float:
    spread_pct = quote.get("spread_pct")
    mid = quote.get("mid")

    if mid is None or spread_pct is None:
        score -= 0.10
        breakdown["liquidity"] -= 0.10
        risks.append("Quote quality unavailable")
        return score

    if spread_pct <= 0.0015:
        score += 0.04
        breakdown["liquidity"] += 0.04
        reasons.append(f"Tight spread: {spread_pct:.2%}")
    elif spread_pct <= config.MAX_SPREAD_PCT:
        score += 0.01
        breakdown["liquidity"] += 0.01
        reasons.append(f"Acceptable spread: {spread_pct:.2%}")
    else:
        score -= 0.14
        breakdown["liquidity"] -= 0.14
        risks.append(f"Wide spread: {spread_pct:.2%}")

    return score


def apply_relative_strength_to_long(score: float, rs: dict, breakdown: dict, reasons: list, risks: list) -> float:
    rs_score = float(rs.get("rs_score", 0.0))
    market_label = rs.get("market_relative_label", "unknown")
    sector_label = rs.get("sector_relative_label", "unknown")
    summary = rs.get("relative_strength_summary", "unknown")

    if rs_score >= 0.20:
        score += 0.12
        breakdown["relative_strength"] += 0.12
        reasons.append(f"Strong relative strength: {summary}")
    elif rs_score >= 0.10:
        score += 0.07
        breakdown["relative_strength"] += 0.07
        reasons.append(f"Positive relative strength: {summary}")
    elif rs_score <= -0.20:
        score -= 0.12
        breakdown["relative_strength"] -= 0.12
        risks.append(f"Weak relative strength for longs: {summary}")
    elif rs_score <= -0.10:
        score -= 0.07
        breakdown["relative_strength"] -= 0.07
        risks.append(f"Negative relative strength for longs: {summary}")

    if market_label in {"strongly_outperforming", "outperforming"}:
        score += 0.03
        breakdown["relative_strength"] += 0.03
        reasons.append(f"Ticker is outperforming SPY: {market_label}")

    if sector_label in {"strongly_outperforming", "outperforming"}:
        score += 0.04
        breakdown["relative_strength"] += 0.04
        reasons.append(f"Ticker is outperforming its sector ETF: {sector_label}")
    elif sector_label in {"strongly_underperforming", "underperforming"}:
        score -= 0.05
        breakdown["relative_strength"] -= 0.05
        risks.append(f"Ticker is lagging its sector ETF: {sector_label}")

    return score


def apply_relative_strength_to_short(score: float, rs: dict, breakdown: dict, reasons: list, risks: list) -> float:
    rs_score = float(rs.get("rs_score", 0.0))
    market_label = rs.get("market_relative_label", "unknown")
    sector_label = rs.get("sector_relative_label", "unknown")
    summary = rs.get("relative_strength_summary", "unknown")

    if rs_score <= -0.20:
        score += 0.12
        breakdown["relative_strength"] += 0.12
        reasons.append(f"Weak relative strength supports short: {summary}")
    elif rs_score <= -0.10:
        score += 0.07
        breakdown["relative_strength"] += 0.07
        reasons.append(f"Negative relative strength supports short: {summary}")
    elif rs_score >= 0.20:
        score -= 0.12
        breakdown["relative_strength"] -= 0.12
        risks.append(f"Strong relative strength is hostile for shorts: {summary}")
    elif rs_score >= 0.10:
        score -= 0.07
        breakdown["relative_strength"] -= 0.07
        risks.append(f"Positive relative strength is hostile for shorts: {summary}")

    if market_label in {"strongly_underperforming", "underperforming"}:
        score += 0.03
        breakdown["relative_strength"] += 0.03
        reasons.append(f"Ticker is underperforming SPY: {market_label}")

    if sector_label in {"strongly_underperforming", "underperforming"}:
        score += 0.04
        breakdown["relative_strength"] += 0.04
        reasons.append(f"Ticker is underperforming its sector ETF: {sector_label}")
    elif sector_label in {"strongly_outperforming", "outperforming"}:
        score -= 0.05
        breakdown["relative_strength"] -= 0.05
        risks.append(f"Ticker is outperforming its sector ETF: {sector_label}")

    return score


def score_long_setup(
    data: dict,
    context: dict,
    sentiment: dict,
    quote: dict,
    rs: dict,
) -> tuple[float, list[str], list[str], dict]:
    regime = context.get("regime", "unknown")

    score = 0.50
    reasons = []
    risks = []

    breakdown = {
        "momentum": 0.0,
        "vwap": 0.0,
        "volume": 0.0,
        "trend": 0.0,
        "context": 0.0,
        "sentiment": 0.0,
        "liquidity": 0.0,
        "relative_strength": 0.0,
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

    score = apply_long_market_context(score, regime, breakdown, reasons, risks)

    if context.get("risk_on_score", 0) >= 0.75:
        score += 0.03
        breakdown["context"] += 0.03
        reasons.append(f"Risk-on score supportive: {context.get('risk_on_score')}")
    elif context.get("risk_on_score", 0) <= 0.25:
        score -= 0.04
        breakdown["context"] -= 0.04
        risks.append(f"Risk-on score weak: {context.get('risk_on_score')}")

    score = apply_sentiment_to_long(score, sentiment, breakdown, reasons, risks)
    score = apply_liquidity_checks(score, quote, breakdown, reasons, risks)
    score = apply_relative_strength_to_long(score, rs, breakdown, reasons, risks)

    if data.get("signal_decay"):
        score -= 0.14
        breakdown["decay"] -= 0.14
        risks.append("Signal decay detected: momentum, volume, or MACD is fading")

    return score, reasons, risks, breakdown


def score_short_setup(
    data: dict,
    context: dict,
    sentiment: dict,
    quote: dict,
    rs: dict,
) -> tuple[float, list[str], list[str], dict]:
    regime = context.get("regime", "unknown")

    score = 0.50
    reasons = []
    risks = []

    breakdown = {
        "momentum": 0.0,
        "vwap": 0.0,
        "volume": 0.0,
        "trend": 0.0,
        "context": 0.0,
        "sentiment": 0.0,
        "liquidity": 0.0,
        "relative_strength": 0.0,
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

    score = apply_short_market_context(score, regime, breakdown, reasons, risks)

    if context.get("risk_on_score", 0) <= 0.25:
        score += 0.03
        breakdown["context"] += 0.03
        reasons.append(f"Risk-on score weak, supportive for shorts: {context.get('risk_on_score')}")
    elif context.get("risk_on_score", 0) >= 0.75:
        score -= 0.04
        breakdown["context"] -= 0.04
        risks.append(f"Risk-on score strong, hostile for shorts: {context.get('risk_on_score')}")

    score = apply_sentiment_to_short(score, sentiment, breakdown, reasons, risks)
    score = apply_liquidity_checks(score, quote, breakdown, reasons, risks)
    score = apply_relative_strength_to_short(score, rs, breakdown, reasons, risks)

    if data.get("signal_decay"):
        score -= 0.12
        breakdown["decay"] -= 0.12
        risks.append("Signal decay detected: momentum, volume, or MACD is fading")

    return score, reasons, risks, breakdown


def choose_direction(long_score: float, short_score: float) -> str:
    if long_score >= config.SIGNAL_MIN_CONFIDENCE and long_score >= short_score + 0.08:
        return "BUY"

    if config.ENABLE_SHORT_SIGNALS and short_score >= config.SIGNAL_MIN_CONFIDENCE and short_score >= long_score + 0.08:
        return "SELL"

    return "HOLD"


def generate_signal(ticker: str, context: dict | None = None) -> dict:
    data = get_indicator_snapshot(ticker)
    if not data:
        return {}

    if context is None:
        context = get_market_context()

    regime = context.get("regime", "unknown")
    sentiment = get_sentiment_snapshot(ticker)
    quote = get_latest_quote(ticker)
    rs = get_relative_strength_snapshot(ticker)

    long_score, long_reasons, long_risks, long_breakdown = score_long_setup(data, context, sentiment, quote, rs)
    short_score, short_reasons, short_risks, short_breakdown = score_short_setup(data, context, sentiment, quote, rs)

    long_confidence = clamp(long_score)
    short_confidence = clamp(short_score)

    if not config.ENABLE_SHORT_SIGNALS:
        short_confidence = 0.0

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

    spread_pct = quote.get("spread_pct")
    if signal in {"BUY", "SELL"} and spread_pct is not None and spread_pct > config.MAX_SPREAD_PCT:
        risks.append(f"Blocked by wide spread: {spread_pct:.2%}")
        signal = "HOLD"
        confidence = min(confidence, 0.60)

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
        "volatility_level": context.get("volatility_level", "unknown"),
        "risk_on_score": context.get("risk_on_score", 0.0),

        "sentiment_score": round(float(sentiment.get("sentiment_score", 0.0)), 4),
        "sentiment_label": sentiment.get("sentiment_label", "neutral"),
        "mention_spike": bool(sentiment.get("mention_spike", False)),
        "article_count": int(sentiment.get("article_count", 0)),
        "top_catalyst": sentiment.get("top_catalyst"),
        "catalyst_flags": sentiment.get("catalyst_flags", []),
        "recent_headlines": sentiment.get("recent_headlines", []),

        "sector_etf": rs.get("sector_etf"),
        "rs_score": round(float(rs.get("rs_score", 0.0)), 4),
        "market_relative_label": rs.get("market_relative_label"),
        "qqq_relative_label": rs.get("qqq_relative_label"),
        "sector_relative_label": rs.get("sector_relative_label"),
        "relative_strength_summary": rs.get("relative_strength_summary"),
        "rs_vs_spy_5m": rs.get("rs_vs_spy_5m"),
        "rs_vs_spy_15m": rs.get("rs_vs_spy_15m"),
        "rs_vs_spy_30m": rs.get("rs_vs_spy_30m"),
        "rs_vs_qqq_5m": rs.get("rs_vs_qqq_5m"),
        "rs_vs_qqq_15m": rs.get("rs_vs_qqq_15m"),
        "rs_vs_qqq_30m": rs.get("rs_vs_qqq_30m"),
        "rs_vs_sector_5m": rs.get("rs_vs_sector_5m"),
        "rs_vs_sector_15m": rs.get("rs_vs_sector_15m"),
        "rs_vs_sector_30m": rs.get("rs_vs_sector_30m"),

        "spread_pct": round(spread_pct, 4) if spread_pct is not None else None,
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
