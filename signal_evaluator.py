from collections import defaultdict
from datetime import datetime, timezone

from market_data import get_latest_price
from redis_store import store


SIGNAL_LOG_KEY = "signal_log"
SIGNAL_LOG_TTL = 60 * 60 * 24 * 14
MAX_SIGNAL_LOG_RECORDS = 5000

EVALUATION_HORIZONS_MINUTES = [5, 15, 30, 60]
CONFIDENCE_BUCKETS = [
    (0.00, 0.60, "<0.60"),
    (0.60, 0.70, "0.60-0.69"),
    (0.70, 0.80, "0.70-0.79"),
    (0.80, 0.90, "0.80-0.89"),
    (0.90, 1.01, "0.90+"),
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def minutes_since(timestamp: str | None) -> float:
    dt = parse_iso(timestamp)
    if not dt:
        return 0.0

    return max((utc_now() - dt).total_seconds() / 60.0, 0.0)


def get_confidence_bucket(confidence: float) -> str:
    for low, high, label in CONFIDENCE_BUCKETS:
        if low <= confidence < high:
            return label
    return "unknown"


def normalize_return(entry_price: float, current_price: float, signal: str) -> float:
    if not entry_price or not current_price:
        return 0.0

    raw_return = (current_price - entry_price) / entry_price

    if signal == "SELL":
        return -raw_return
    return raw_return


def build_signal_record(signal: dict) -> dict:
    confidence = float(signal.get("confidence", 0.0))

    return {
        "id": (
            f"{signal.get('ticker', 'UNKNOWN')}-"
            f"{signal.get('signal', 'HOLD')}-"
            f"{signal.get('timestamp', utc_now_iso())}"
        ),
        "timestamp": signal.get("timestamp", utc_now_iso()),
        "ticker": signal.get("ticker"),
        "signal": signal.get("signal", "HOLD"),
        "confidence": confidence,
        "confidence_bucket": get_confidence_bucket(confidence),

        "entry_price": signal.get("price"),
        "entry_zone": signal.get("entry_zone"),
        "stop": signal.get("stop"),
        "target": signal.get("target"),
        "risk_reward": signal.get("risk_reward"),

        "regime": signal.get("regime"),
        "volatility_level": signal.get("volatility_level"),
        "risk_on_score": signal.get("risk_on_score"),

        "sentiment_label": signal.get("sentiment_label"),
        "sentiment_score": signal.get("sentiment_score"),
        "mention_spike": signal.get("mention_spike"),
        "article_count": signal.get("article_count"),
        "top_catalyst": signal.get("top_catalyst"),

        "sector_etf": signal.get("sector_etf"),
        "rs_score": signal.get("rs_score"),
        "market_relative_label": signal.get("market_relative_label"),
        "sector_relative_label": signal.get("sector_relative_label"),
        "relative_strength_summary": signal.get("relative_strength_summary"),

        "signal_memory_state": signal.get("signal_memory_state"),
        "signal_persistence": signal.get("signal_persistence"),
        "confidence_delta": signal.get("confidence_delta"),
        "momentum_delta": signal.get("momentum_delta"),
        "volume_delta": signal.get("volume_delta"),

        "momentum_5m": signal.get("momentum_5m"),
        "momentum_15m": signal.get("momentum_15m"),
        "momentum_30m": signal.get("momentum_30m"),
        "momentum_acceleration": signal.get("momentum_acceleration"),
        "volume_ratio": signal.get("volume_ratio"),
        "spread_pct": signal.get("spread_pct"),
        "vwap_state": signal.get("vwap_state"),
        "vwap_distance": signal.get("vwap_distance"),
        "rsi": signal.get("rsi"),
        "adx": signal.get("adx"),
        "signal_decay": signal.get("signal_decay"),

        "reasons": signal.get("reasons", []),
        "risks": signal.get("risks", []),

        "latest_price": signal.get("price"),
        "latest_update": utc_now_iso(),

        "max_favorable_return": 0.0,
        "max_adverse_return": 0.0,

        "horizons": {
            str(h): {
                "evaluated": False,
                "elapsed_minutes": 0.0,
                "return": None,
                "win": None,
                "stop_hit": False,
                "target_hit": False,
            }
            for h in EVALUATION_HORIZONS_MINUTES
        },
    }


def load_signal_log() -> list[dict]:
    return store.get_json(SIGNAL_LOG_KEY, default=[]) or []


def save_signal_log(records: list[dict]):
    trimmed = records[-MAX_SIGNAL_LOG_RECORDS:]
    store.set_json(SIGNAL_LOG_KEY, trimmed, ttl=SIGNAL_LOG_TTL)


def append_signal_batch(signals: list[dict]):
    if not signals:
        return

    records = load_signal_log()
    existing_ids = {record.get("id") for record in records}

    new_records = []
    for signal in signals:
        if signal.get("signal") not in {"BUY", "SELL"}:
            continue
        if not signal.get("ticker") or not signal.get("price"):
            continue

        record = build_signal_record(signal)
        if record["id"] in existing_ids:
            continue

        existing_ids.add(record["id"])
        new_records.append(record)

    if new_records:
        records.extend(new_records)
        save_signal_log(records)


def update_record_with_price(record: dict, current_price: float):
    entry_price = float(record.get("entry_price") or 0.0)
    signal = record.get("signal", "HOLD")

    if entry_price <= 0 or current_price <= 0:
        return

    current_return = normalize_return(entry_price, current_price, signal)

    record["latest_price"] = round(current_price, 4)
    record["latest_update"] = utc_now_iso()
    record["max_favorable_return"] = round(
        max(float(record.get("max_favorable_return", 0.0)), current_return),
        4,
    )
    record["max_adverse_return"] = round(
        min(float(record.get("max_adverse_return", 0.0)), current_return),
        4,
    )


def update_horizon_outcomes(record: dict, current_price: float):
    entry_price = float(record.get("entry_price") or 0.0)
    signal = record.get("signal", "HOLD")
    stop = record.get("stop")
    target = record.get("target")

    if entry_price <= 0 or current_price <= 0:
        return

    elapsed_minutes = minutes_since(record.get("timestamp"))
    current_return = normalize_return(entry_price, current_price, signal)

    for horizon in EVALUATION_HORIZONS_MINUTES:
        bucket = record["horizons"][str(horizon)]

        if bucket["evaluated"]:
            continue

        bucket["elapsed_minutes"] = round(elapsed_minutes, 2)

        if stop:
            if signal == "BUY" and current_price <= float(stop):
                bucket["stop_hit"] = True
            elif signal == "SELL" and current_price >= float(stop):
                bucket["stop_hit"] = True

        if target:
            if signal == "BUY" and current_price >= float(target):
                bucket["target_hit"] = True
            elif signal == "SELL" and current_price <= float(target):
                bucket["target_hit"] = True

        if elapsed_minutes >= horizon:
            bucket["evaluated"] = True
            bucket["return"] = round(current_return, 4)
            bucket["win"] = current_return > 0


def evaluate_pending_signals():
    records = load_signal_log()
    if not records:
        return

    updated = False

    for record in records:
        ticker = record.get("ticker")
        signal = record.get("signal")

        if not ticker or signal not in {"BUY", "SELL"}:
            continue

        if all(record["horizons"][str(h)]["evaluated"] for h in EVALUATION_HORIZONS_MINUTES):
            continue

        current_price = get_latest_price(ticker)
        if not current_price:
            continue

        update_record_with_price(record, float(current_price))
        update_horizon_outcomes(record, float(current_price))
        updated = True

    if updated:
        save_signal_log(records)


def get_recent_signal_log(limit: int = 100) -> list[dict]:
    records = load_signal_log()
    return records[-limit:][::-1]


def summarize_signal_performance() -> dict:
    records = load_signal_log()

    summary = {
        "total_logged_signals": len(records),
        "by_horizon": {},
        "by_confidence_bucket": {},
        "by_signal_type": {},
    }

    for horizon in EVALUATION_HORIZONS_MINUTES:
        horizon_key = str(horizon)
        evaluated = [
            record for record in records
            if record.get("horizons", {}).get(horizon_key, {}).get("evaluated")
        ]

        if not evaluated:
            summary["by_horizon"][horizon_key] = {
                "count": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "avg_mfe": 0.0,
                "avg_mae": 0.0,
                "target_hit_rate": 0.0,
                "stop_hit_rate": 0.0,
            }
            continue

        wins = 0
        returns = []
        mfes = []
        maes = []
        target_hits = 0
        stop_hits = 0

        for record in evaluated:
            outcome = record["horizons"][horizon_key]
            ret = float(outcome.get("return") or 0.0)

            returns.append(ret)
            mfes.append(float(record.get("max_favorable_return", 0.0)))
            maes.append(float(record.get("max_adverse_return", 0.0)))

            if outcome.get("win"):
                wins += 1
            if outcome.get("target_hit"):
                target_hits += 1
            if outcome.get("stop_hit"):
                stop_hits += 1

        count = len(evaluated)

        summary["by_horizon"][horizon_key] = {
            "count": count,
            "win_rate": round(wins / count, 4),
            "avg_return": round(sum(returns) / count, 4),
            "avg_mfe": round(sum(mfes) / count, 4),
            "avg_mae": round(sum(maes) / count, 4),
            "target_hit_rate": round(target_hits / count, 4),
            "stop_hit_rate": round(stop_hits / count, 4),
        }

    bucket_stats = defaultdict(lambda: {
        "count": 0,
        "wins_15m": 0,
        "avg_return_15m_sum": 0.0,
    })

    signal_type_stats = defaultdict(lambda: {
        "count": 0,
        "wins_15m": 0,
        "avg_return_15m_sum": 0.0,
    })

    for record in records:
        bucket = record.get("confidence_bucket", "unknown")
        signal_type = record.get("signal", "unknown")
        outcome_15m = record.get("horizons", {}).get("15", {})

        if not outcome_15m.get("evaluated"):
            continue

        ret = float(outcome_15m.get("return") or 0.0)
        win = bool(outcome_15m.get("win"))

        bucket_stats[bucket]["count"] += 1
        bucket_stats[bucket]["avg_return_15m_sum"] += ret
        if win:
            bucket_stats[bucket]["wins_15m"] += 1

        signal_type_stats[signal_type]["count"] += 1
        signal_type_stats[signal_type]["avg_return_15m_sum"] += ret
        if win:
            signal_type_stats[signal_type]["wins_15m"] += 1

    for bucket, stats in bucket_stats.items():
        count = stats["count"]
        summary["by_confidence_bucket"][bucket] = {
            "count": count,
            "win_rate_15m": round(stats["wins_15m"] / count, 4) if count else 0.0,
            "avg_return_15m": round(stats["avg_return_15m_sum"] / count, 4) if count else 0.0,
        }

    for signal_type, stats in signal_type_stats.items():
        count = stats["count"]
        summary["by_signal_type"][signal_type] = {
            "count": count,
            "win_rate_15m": round(stats["wins_15m"] / count, 4) if count else 0.0,
            "avg_return_15m": round(stats["avg_return_15m_sum"] / count, 4) if count else 0.0,
        }

    return summary
