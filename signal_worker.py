import time
from datetime import datetime, timezone

from config import config
from redis_store import store
from signal_engine import generate_signals
from watchlist_engine import get_active_watchlist
from market_context import get_market_context


def run_worker():
    loop_count = 0

    while True:
        loop_count += 1

        try:
            watchlist = get_active_watchlist(limit=30)
            signals = generate_signals(watchlist)
            context = get_market_context()

            high_quality = [
                signal for signal in signals
                if signal["confidence"] >= config.HIGH_QUALITY_SIGNAL_CONFIDENCE
                and signal["signal"] in {"BUY", "SELL"}
            ]

            store.set_json("live_signals", signals, ttl=120)
            store.set_json("high_quality_signals", high_quality, ttl=120)
            store.set_json("market_context", context, ttl=120)
            store.set_json(
                "worker_heartbeat",
                {
                    "status": "running",
                    "loop_count": loop_count,
                    "last_update": datetime.now(timezone.utc).isoformat(),
                    "signals": len(signals),
                    "high_quality": len(high_quality),
                },
                ttl=120,
            )

            print(
                f"[signal_worker] loop={loop_count} "
                f"signals={len(signals)} high_quality={len(high_quality)}"
            )

        except Exception as exc:
            store.set_json(
                "worker_heartbeat",
                {
                    "status": "error",
                    "loop_count": loop_count,
                    "error": str(exc),
                    "last_update": datetime.now(timezone.utc).isoformat(),
                },
                ttl=120,
            )
            print(f"[signal_worker] error: {exc}")

        time.sleep(config.SIGNAL_LOOP_SECONDS)


if __name__ == "__main__":
    run_worker()
