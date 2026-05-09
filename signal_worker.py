import time
from datetime import datetime, time as dt_time, timezone
from zoneinfo import ZoneInfo

from config import config
from redis_store import store
from signal_engine import generate_signals
from watchlist_engine import get_active_watchlist
from market_context import get_market_context


MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = dt_time(9, 30)
MARKET_CLOSE = dt_time(16, 0)

SIGNAL_HISTORY_KEY = "signal_history"
SIGNAL_HISTORY_LENGTH = 5
SIGNAL_HISTORY_TTL = 60 * 60 * 6


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_market_hours() -> bool:
    now_et = datetime.now(MARKET_TZ)

    if now_et.weekday() >= 5:
        return False

    current_time = now_et.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def get_top_actionable_signal(signals: list[dict]) -> dict | None:
    actionable = [
        signal for signal in signals
        if signal.get("signal") in {"BUY", "SELL"}
        and signal.get("confidence", 0) >= config.HIGH_QUALITY_SIGNAL_CONFIDENCE
        and signal.get("risk_reward", 0) >= config.MIN_RISK_REWARD
        and not signal.get("signal_decay", False)
    ]

    if not actionable:
        return None

    return sorted(actionable, key=lambda item: item.get("confidence", 0), reverse=True)[0]


def should_trigger_ding(current_alert: dict | None, previous_alert: dict | None) -> bool:
    if not current_alert:
        return False

    if not previous_alert or not previous_alert.get("active"):
        return True

    current_key = f"{current_alert.get('ticker')}:{current_alert.get('signal')}"
    previous_key = f"{previous_alert.get('ticker')}:{previous_alert.get('signal')}"

    if current_key != previous_key:
        return True

    current_confidence = float(current_alert.get("confidence", 0))
    previous_confidence = float(previous_alert.get("confidence", 0))

    if (
        current_confidence >= config.HIGH_QUALITY_SIGNAL_CONFIDENCE
        and current_confidence - previous_confidence >= 0.05
    ):
        return True

    if current_alert.get("signal_memory_state") == "strengthening":
        return True

    return False


def _build_memory_snapshot(signal: dict) -> dict:
    return {
        "signal": signal.get("signal"),
        "confidence": float(signal.get("confidence", 0)),
        "momentum_5m": float(signal.get("momentum_5m", 0)),
        "momentum_15m": float(signal.get("momentum_15m", 0)),
        "momentum_acceleration": float(signal.get("momentum_acceleration", 0)),
        "volume_ratio": float(signal.get("volume_ratio", 0)),
        "sentiment_score": float(signal.get("sentiment_score", 0)),
        "timestamp": signal.get("timestamp", utc_now_iso()),
    }


def _classify_signal_memory(current_signal: dict, prior_history: list[dict]) -> dict:
    if not prior_history:
        return {
            "signal_memory_state": "new",
            "signal_persistence": 1,
            "confidence_delta": 0.0,
            "momentum_delta": 0.0,
            "volume_delta": 0.0,
        }

    last = prior_history[-1]

    current_direction = current_signal.get("signal", "HOLD")
    previous_direction = last.get("signal", "HOLD")

    current_confidence = float(current_signal.get("confidence", 0))
    previous_confidence = float(last.get("confidence", 0))

    current_momentum = float(current_signal.get("momentum_15m", 0))
    previous_momentum = float(last.get("momentum_15m", 0))

    current_volume = float(current_signal.get("volume_ratio", 0))
    previous_volume = float(last.get("volume_ratio", 0))

    confidence_delta = current_confidence - previous_confidence
    momentum_delta = current_momentum - previous_momentum
    volume_delta = current_volume - previous_volume

    persistence = 1
    for snapshot in reversed(prior_history):
        if snapshot.get("signal") == current_direction:
            persistence += 1
        else:
            break

    if previous_direction != current_direction and current_direction != "HOLD":
        state = "reversing"
    elif current_direction == "HOLD":
        if confidence_delta < -0.03:
            state = "fading"
        else:
            state = "stable"
    elif (
        confidence_delta >= 0.03
        and (
            (current_direction == "BUY" and momentum_delta >= 0)
            or (current_direction == "SELL" and momentum_delta <= 0)
        )
        and volume_delta >= -0.10
    ):
        state = "strengthening"
    elif confidence_delta <= -0.03 or abs(volume_delta) > 0.35:
        state = "fading"
    else:
        state = "stable"

    return {
        "signal_memory_state": state,
        "signal_persistence": persistence,
        "confidence_delta": round(confidence_delta, 4),
        "momentum_delta": round(momentum_delta, 4),
        "volume_delta": round(volume_delta, 4),
    }


def enrich_signals_with_memory(signals: list[dict]) -> tuple[list[dict], dict]:
    signal_history = store.get_json(SIGNAL_HISTORY_KEY, default={}) or {}
    updated_history = {}

    enriched = []

    for signal in signals:
        ticker = signal.get("ticker")
        if not ticker:
            continue

        prior_history = signal_history.get(ticker, []) or []
        memory = _classify_signal_memory(signal, prior_history)

        signal["signal_memory_state"] = memory["signal_memory_state"]
        signal["signal_persistence"] = memory["signal_persistence"]
        signal["confidence_delta"] = memory["confidence_delta"]
        signal["momentum_delta"] = memory["momentum_delta"]
        signal["volume_delta"] = memory["volume_delta"]

        new_snapshot = _build_memory_snapshot(signal)
        updated_history[ticker] = (prior_history + [new_snapshot])[-SIGNAL_HISTORY_LENGTH:]

        enriched.append(signal)

    for ticker, history in signal_history.items():
        if ticker not in updated_history:
            updated_history[ticker] = history[-SIGNAL_HISTORY_LENGTH:]

    return enriched, updated_history


def build_alert_payload(top_signal: dict | None, previous_alert: dict | None) -> dict:
    should_ding = should_trigger_ding(top_signal, previous_alert)

    if not top_signal:
        return {
            "active": False,
            "should_ding": False,
            "ticker": None,
            "signal": "HOLD",
            "confidence": 0,
            "message": "No actionable signal",
            "timestamp": utc_now_iso(),
        }

    return {
        "active": True,
        "should_ding": should_ding,
        "ticker": top_signal.get("ticker"),
        "signal": top_signal.get("signal"),
        "confidence": top_signal.get("confidence"),
        "long_confidence": top_signal.get("long_confidence"),
        "short_confidence": top_signal.get("short_confidence"),
        "price": top_signal.get("price"),
        "entry_zone": top_signal.get("entry_zone"),
        "stop": top_signal.get("stop"),
        "target": top_signal.get("target"),
        "risk_reward": top_signal.get("risk_reward"),
        "message": f"DING — {top_signal.get('signal')} {top_signal.get('ticker')} NOW",
        "regime": top_signal.get("regime"),
        "volatility_level": top_signal.get("volatility_level"),
        "risk_on_score": top_signal.get("risk_on_score"),
        "sentiment_score": top_signal.get("sentiment_score"),
        "sentiment_label": top_signal.get("sentiment_label"),
        "mention_spike": top_signal.get("mention_spike"),
        "article_count": top_signal.get("article_count"),
        "top_catalyst": top_signal.get("top_catalyst"),
        "catalyst_flags": top_signal.get("catalyst_flags", []),
        "recent_headlines": top_signal.get("recent_headlines", []),
        "spread_pct": top_signal.get("spread_pct"),
        "volume_ratio": top_signal.get("volume_ratio"),
        "volume_ratio_60": top_signal.get("volume_ratio_60"),
        "momentum_5m": top_signal.get("momentum_5m"),
        "momentum_15m": top_signal.get("momentum_15m"),
        "momentum_30m": top_signal.get("momentum_30m"),
        "momentum_acceleration": top_signal.get("momentum_acceleration"),
        "vwap_distance": top_signal.get("vwap_distance"),
        "vwap_state": top_signal.get("vwap_state"),
        "rsi": top_signal.get("rsi"),
        "adx": top_signal.get("adx"),
        "macd_histogram": top_signal.get("macd_histogram"),
        "macd_histogram_rising": top_signal.get("macd_histogram_rising"),
        "distance_to_support": top_signal.get("distance_to_support"),
        "distance_to_resistance": top_signal.get("distance_to_resistance"),
        "signal_decay": top_signal.get("signal_decay"),
        "signal_memory_state": top_signal.get("signal_memory_state"),
        "signal_persistence": top_signal.get("signal_persistence"),
        "confidence_delta": top_signal.get("confidence_delta"),
        "momentum_delta": top_signal.get("momentum_delta"),
        "volume_delta": top_signal.get("volume_delta"),
        "breakdown": top_signal.get("breakdown", {}),
        "reasons": top_signal.get("reasons", []),
        "risks": top_signal.get("risks", []),
        "timestamp": utc_now_iso(),
    }


def write_heartbeat(status: str, loop_count: int, extra: dict | None = None):
    payload = {
        "status": status,
        "loop_count": loop_count,
        "last_update": utc_now_iso(),
    }

    if extra:
        payload.update(extra)

    store.set_json("worker_heartbeat", payload, ttl=180)


def clear_market_state(status: str, loop_count: int, context: dict | None = None):
    store.set_json("live_signals", [], ttl=180)
    store.set_json("high_quality_signals", [], ttl=180)
    store.set_json(
        "latest_alert",
        {
            "active": False,
            "should_ding": False,
            "ticker": None,
            "signal": "HOLD",
            "confidence": 0,
            "message": status,
            "timestamp": utc_now_iso(),
        },
        ttl=180,
    )

    if context:
        store.set_json("market_context", context, ttl=180)

    write_heartbeat(
        status=status,
        loop_count=loop_count,
        extra={
            "signals": 0,
            "high_quality": 0,
            "market_open": False,
        },
    )


def run_worker():
    loop_count = 0

    while True:
        loop_count += 1

        try:
            context = get_market_context()
            store.set_json("market_context", context, ttl=180)

            if not is_market_hours():
                clear_market_state(
                    status="market_closed",
                    loop_count=loop_count,
                    context=context,
                )
                print(f"[signal_worker] loop={loop_count} market_closed")
                time.sleep(config.SIGNAL_LOOP_SECONDS)
                continue

            previous_alert = store.get_json("latest_alert", default=None)

            watchlist = get_active_watchlist(limit=config.WATCHLIST_LIMIT)
            signals = generate_signals(watchlist)
            signals, signal_history = enrich_signals_with_memory(signals)

            high_quality = [
                signal for signal in signals
                if signal.get("confidence", 0) >= config.HIGH_QUALITY_SIGNAL_CONFIDENCE
                and signal.get("signal") in {"BUY", "SELL"}
                and signal.get("risk_reward", 0) >= config.MIN_RISK_REWARD
                and not signal.get("signal_decay", False)
            ]

            top_signal = get_top_actionable_signal(signals)
            latest_alert = build_alert_payload(top_signal, previous_alert)

            store.set_json(SIGNAL_HISTORY_KEY, signal_history, ttl=SIGNAL_HISTORY_TTL)
            store.set_json("live_signals", signals, ttl=180)
            store.set_json("high_quality_signals", high_quality, ttl=180)
            store.set_json("latest_alert", latest_alert, ttl=180)

            write_heartbeat(
                status="running",
                loop_count=loop_count,
                extra={
                    "signals": len(signals),
                    "high_quality": len(high_quality),
                    "market_open": True,
                    "watchlist_size": len(watchlist),
                    "latest_alert": latest_alert.get("message"),
                    "top_catalyst": latest_alert.get("top_catalyst"),
                    "sentiment_label": latest_alert.get("sentiment_label"),
                    "signal_memory_state": latest_alert.get("signal_memory_state"),
                },
            )

            print(
                f"[signal_worker] loop={loop_count} "
                f"signals={len(signals)} "
                f"high_quality={len(high_quality)} "
                f"alert={latest_alert.get('message')} "
                f"catalyst={latest_alert.get('top_catalyst')} "
                f"sentiment={latest_alert.get('sentiment_label')} "
                f"memory={latest_alert.get('signal_memory_state')}"
            )

        except Exception as exc:
            write_heartbeat(
                status="error",
                loop_count=loop_count,
                extra={
                    "error": str(exc),
                    "market_open": is_market_hours(),
                },
            )
            print(f"[signal_worker] error: {exc}")

        time.sleep(config.SIGNAL_LOOP_SECONDS)


if __name__ == "__main__":
    run_worker()
