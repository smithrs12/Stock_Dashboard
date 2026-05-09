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

    if not previous_alert:
        return True

    current_key = f"{current_alert.get('ticker')}:{current_alert.get('signal')}"
    previous_key = f"{previous_alert.get('ticker')}:{previous_alert.get('signal')}"

    if current_key != previous_key:
        return True

    current_confidence = current_alert.get("confidence", 0)
    previous_confidence = previous_alert.get("confidence", 0)

    if current_confidence >= config.HIGH_QUALITY_SIGNAL_CONFIDENCE and current_confidence - previous_confidence >= 0.05:
        return True

    return False


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
        "price": top_signal.get("price"),
        "entry_zone": top_signal.get("entry_zone"),
        "stop": top_signal.get("stop"),
        "target": top_signal.get("target"),
        "risk_reward": top_signal.get("risk_reward"),
        "message": f"DING — {top_signal.get('signal')} {top_signal.get('ticker')} NOW",
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

            watchlist = get_active_watchlist(limit=30)
            signals = generate_signals(watchlist)

            high_quality = [
                signal for signal in signals
                if signal.get("confidence", 0) >= config.HIGH_QUALITY_SIGNAL_CONFIDENCE
                and signal.get("signal") in {"BUY", "SELL"}
                and signal.get("risk_reward", 0) >= config.MIN_RISK_REWARD
                and not signal.get("signal_decay", False)
            ]

            top_signal = get_top_actionable_signal(signals)
            latest_alert = build_alert_payload(top_signal, previous_alert)

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
                },
            )

            print(
                f"[signal_worker] loop={loop_count} "
                f"signals={len(signals)} "
                f"high_quality={len(high_quality)} "
                f"alert={latest_alert.get('message')}"
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
