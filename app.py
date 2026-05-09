import time

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from redis_store import store


ALERT_COOLDOWN_SECONDS = 30


st.set_page_config(
    page_title="Trading Intelligence Engine",
    layout="wide",
)

st_autorefresh(interval=15_000, key="refresh")


def signal_color(signal: str) -> str:
    if signal == "BUY":
        return "#16a34a"
    if signal == "SELL":
        return "#dc2626"
    return "#eab308"


def signal_label(signal: str) -> str:
    if signal == "BUY":
        return "DING — BUY NOW"
    if signal == "SELL":
        return "DING — SELL NOW"
    return "YELLOW DOT — HOLD"


def sentiment_color(label: str) -> str:
    if label == "bullish":
        return "#16a34a"
    if label == "bearish":
        return "#dc2626"
    return "#94a3b8"


def memory_color(state: str) -> str:
    if state == "strengthening":
        return "#16a34a"
    if state == "fading":
        return "#dc2626"
    if state == "reversing":
        return "#f97316"
    if state == "new":
        return "#38bdf8"
    return "#94a3b8"


def rs_color(summary: str) -> str:
    if summary in {"leading_market_and_sector", "leading_market", "leading_sector"}:
        return "#16a34a"
    if summary in {"lagging_market_and_sector", "lagging_market", "lagging_sector"}:
        return "#dc2626"
    return "#94a3b8"


def render_sentiment_chip(label: str, score: float):
    color = sentiment_color(label)
    st.markdown(
        f"""
        <div style="
            display: inline-block;
            border: 1px solid {color};
            color: {color};
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 14px;
            font-weight: 700;
            margin-right: 8px;
            margin-bottom: 8px;
        ">
            Sentiment: {label.upper()} ({score:.2f})
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_memory_chip(state: str, persistence: int):
    color = memory_color(state)
    st.markdown(
        f"""
        <div style="
            display: inline-block;
            border: 1px solid {color};
            color: {color};
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 14px;
            font-weight: 700;
            margin-right: 8px;
            margin-bottom: 8px;
        ">
            Signal Memory: {state.upper()} (cycles: {persistence})
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_rs_chip(summary: str, sector_etf: str | None, rs_score: float):
    color = rs_color(summary)
    sector_text = sector_etf or "N/A"
    st.markdown(
        f"""
        <div style="
            display: inline-block;
            border: 1px solid {color};
            color: {color};
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 14px;
            font-weight: 700;
            margin-right: 8px;
            margin-bottom: 8px;
        ">
            RS: {summary.upper()} | Sector ETF: {sector_text} | Score: {rs_score:.2f}
        </div>
        """,
        unsafe_allow_html=True,
    )


def maybe_play_alert_sound(latest_alert: dict):
    if "last_ding_key" not in st.session_state:
        st.session_state.last_ding_key = None

    if "last_ding_ts" not in st.session_state:
        st.session_state.last_ding_ts = 0.0

    if not latest_alert or not latest_alert.get("active"):
        return

    if latest_alert.get("signal") not in {"BUY", "SELL"}:
        return

    if not latest_alert.get("should_ding"):
        return

    alert_key = (
        f"{latest_alert.get('ticker')}|"
        f"{latest_alert.get('signal')}|"
        f"{latest_alert.get('confidence')}|"
        f"{latest_alert.get('timestamp')}"
    )

    now_ts = time.time()
    within_cooldown = (now_ts - st.session_state.last_ding_ts) < ALERT_COOLDOWN_SECONDS

    if st.session_state.last_ding_key == alert_key or within_cooldown:
        return

    st.session_state.last_ding_key = alert_key
    st.session_state.last_ding_ts = now_ts

    components.html(
        """
        <script>
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
            const ctx = new AudioContextClass();

            function beep(freq, start, duration, gainValue) {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();

                osc.type = "sine";
                osc.frequency.value = freq;

                gain.gain.setValueAtTime(0.0001, start);
                gain.gain.exponentialRampToValueAtTime(gainValue, start + 0.01);
                gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);

                osc.connect(gain);
                gain.connect(ctx.destination);

                osc.start(start);
                osc.stop(start + duration + 0.02);
            }

            const t = ctx.currentTime + 0.02;
            beep(880, t, 0.10, 0.08);
            beep(1175, t + 0.14, 0.14, 0.08);
        }
        </script>
        """,
        height=0,
    )


def render_signal_card(item: dict, featured: bool = False):
    signal = item.get("signal", "HOLD")
    color = signal_color(signal)

    border_width = "5px" if featured else "2px"
    font_size = "42px" if featured else "28px"

    st.markdown(
        f"""
        <div style="
            border: {border_width} solid {color};
            border-radius: 18px;
            padding: 22px;
            margin-bottom: 18px;
            background: rgba(255,255,255,0.03);
        ">
            <div style="
                display: flex;
                align-items: center;
                gap: 18px;
                margin-bottom: 8px;
            ">
                <div style="
                    width: 34px;
                    height: 34px;
                    border-radius: 50%;
                    background: {color};
                    box-shadow: 0 0 18px {color};
                "></div>
                <div style="font-size: {font_size}; font-weight: 800;">
                    {signal_label(signal)} — {item.get("ticker")}
                </div>
            </div>
            <div style="font-size: 18px; opacity: 0.85;">
                Confidence: <strong>{item.get("confidence", 0):.2f}</strong>
                &nbsp; | &nbsp;
                Price: <strong>{item.get("price")}</strong>
                &nbsp; | &nbsp;
                Regime: <strong>{item.get("regime")}</strong>
                &nbsp; | &nbsp;
                Catalyst: <strong>{item.get("top_catalyst") or "none"}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    cols[0].metric("Entry", item.get("entry_zone"))
    cols[1].metric("Stop", item.get("stop"))
    cols[2].metric("Target", item.get("target"))
    cols[3].metric("R/R", item.get("risk_reward"))

    subcols = st.columns(4)
    subcols[0].metric("Sentiment", item.get("sentiment_label", "neutral"))
    subcols[1].metric("Sentiment Score", item.get("sentiment_score", 0.0))
    subcols[2].metric("Articles", item.get("article_count", 0))
    subcols[3].metric("Mention Spike", "Yes" if item.get("mention_spike") else "No")

    memory_cols = st.columns(4)
    memory_cols[0].metric("Memory State", item.get("signal_memory_state", "unknown"))
    memory_cols[1].metric("Persistence", item.get("signal_persistence", 0))
    memory_cols[2].metric("Confidence Δ", item.get("confidence_delta", 0.0))
    memory_cols[3].metric("Momentum Δ", item.get("momentum_delta", 0.0))

    rs_cols = st.columns(4)
    rs_cols[0].metric("Sector ETF", item.get("sector_etf", "N/A"))
    rs_cols[1].metric("RS Score", item.get("rs_score", 0.0))
    rs_cols[2].metric("vs Market", item.get("market_relative_label", "unknown"))
    rs_cols[3].metric("vs Sector", item.get("sector_relative_label", "unknown"))

    render_sentiment_chip(
        item.get("sentiment_label", "neutral"),
        float(item.get("sentiment_score", 0.0)),
    )
    render_memory_chip(
        item.get("signal_memory_state", "unknown"),
        int(item.get("signal_persistence", 0)),
    )
    render_rs_chip(
        item.get("relative_strength_summary", "unknown"),
        item.get("sector_etf"),
        float(item.get("rs_score", 0.0)),
    )

    if item.get("catalyst_flags"):
        st.markdown(
            f"**Catalysts:** {', '.join(item.get('catalyst_flags', []))}"
        )

    with st.expander("Why this signal?"):
        st.markdown("**Reasons**")
        for reason in item.get("reasons", []):
            st.write(f"- {reason}")

        if item.get("risks"):
            st.markdown("**Risks**")
            for risk in item.get("risks", []):
                st.write(f"- {risk}")

        if item.get("breakdown"):
            st.markdown("**Confidence Breakdown**")
            st.json(item.get("breakdown"))

        st.markdown("**Signal Memory**")
        st.write(f"- State: {item.get('signal_memory_state', 'unknown')}")
        st.write(f"- Persistence: {item.get('signal_persistence', 0)} cycles")
        st.write(f"- Confidence delta: {item.get('confidence_delta', 0.0)}")
        st.write(f"- Momentum delta: {item.get('momentum_delta', 0.0)}")
        st.write(f"- Volume delta: {item.get('volume_delta', 0.0)}")

        st.markdown("**Relative Strength**")
        st.write(f"- Sector ETF: {item.get('sector_etf', 'N/A')}")
        st.write(f"- RS score: {item.get('rs_score', 0.0)}")
        st.write(f"- Market label: {item.get('market_relative_label', 'unknown')}")
        st.write(f"- QQQ label: {item.get('qqq_relative_label', 'unknown')}")
        st.write(f"- Sector label: {item.get('sector_relative_label', 'unknown')}")
        st.write(f"- Summary: {item.get('relative_strength_summary', 'unknown')}")

        headlines = item.get("recent_headlines", [])
        if headlines:
            st.markdown("**Recent Headlines**")
            for headline in headlines[:5]:
                title = headline.get("headline", "Untitled")
                source = headline.get("source", "Unknown")
                created_at = headline.get("created_at", "")
                catalysts = headline.get("catalysts", [])
                score = headline.get("sentiment_score", 0.0)

                st.markdown(
                    f"- **{title}**  \n"
                    f"  Source: {source} | Score: {score:.2f} | "
                    f"Catalysts: {', '.join(catalysts) if catalysts else 'none'} | "
                    f"Time: {created_at}"
                )


def render_latest_alert(latest_alert: dict):
    st.divider()
    st.subheader("Live Trading Alert")

    if latest_alert and latest_alert.get("active"):
        alert_signal = latest_alert.get("signal", "HOLD")
        alert_color = signal_color(alert_signal)

        st.markdown(
            f"""
            <div style="
                border: 6px solid {alert_color};
                border-radius: 22px;
                padding: 28px;
                margin-bottom: 20px;
                background: rgba(255,255,255,0.05);
            ">
                <div style="
                    display: flex;
                    align-items: center;
                    gap: 18px;
                    margin-bottom: 10px;
                ">
                    <div style="
                        width: 40px;
                        height: 40px;
                        border-radius: 50%;
                        background: {alert_color};
                        box-shadow: 0 0 22px {alert_color};
                    "></div>
                    <div style="font-size: 48px; font-weight: 900;">
                        {latest_alert.get("message")}
                    </div>
                </div>

                <div style="font-size: 20px;">
                    Confidence: <strong>{latest_alert.get("confidence", 0):.2f}</strong>
                    &nbsp; | &nbsp;
                    Price: <strong>{latest_alert.get("price")}</strong>
                    &nbsp; | &nbsp;
                    R/R: <strong>{latest_alert.get("risk_reward")}</strong>
                    &nbsp; | &nbsp;
                    Catalyst: <strong>{latest_alert.get("top_catalyst") or "none"}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        cols = st.columns(3)
        cols[0].metric("Entry", latest_alert.get("entry_zone"))
        cols[1].metric("Stop", latest_alert.get("stop"))
        cols[2].metric("Target", latest_alert.get("target"))

        sentiment_cols = st.columns(4)
        sentiment_cols[0].metric("Sentiment", latest_alert.get("sentiment_label", "neutral"))
        sentiment_cols[1].metric("Sentiment Score", latest_alert.get("sentiment_score", 0.0))
        sentiment_cols[2].metric("Articles", latest_alert.get("article_count", 0))
        sentiment_cols[3].metric("Mention Spike", "Yes" if latest_alert.get("mention_spike") else "No")

        memory_cols = st.columns(4)
        memory_cols[0].metric("Memory State", latest_alert.get("signal_memory_state", "unknown"))
        memory_cols[1].metric("Persistence", latest_alert.get("signal_persistence", 0))
        memory_cols[2].metric("Confidence Δ", latest_alert.get("confidence_delta", 0.0))
        memory_cols[3].metric("Momentum Δ", latest_alert.get("momentum_delta", 0.0))

        rs_cols = st.columns(4)
        rs_cols[0].metric("Sector ETF", latest_alert.get("sector_etf", "N/A"))
        rs_cols[1].metric("RS Score", latest_alert.get("rs_score", 0.0))
        rs_cols[2].metric("vs Market", latest_alert.get("market_relative_label", "unknown"))
        rs_cols[3].metric("vs Sector", latest_alert.get("sector_relative_label", "unknown"))

        render_sentiment_chip(
            latest_alert.get("sentiment_label", "neutral"),
            float(latest_alert.get("sentiment_score", 0.0)),
        )
        render_memory_chip(
            latest_alert.get("signal_memory_state", "unknown"),
            int(latest_alert.get("signal_persistence", 0)),
        )
        render_rs_chip(
            latest_alert.get("relative_strength_summary", "unknown"),
            latest_alert.get("sector_etf"),
            float(latest_alert.get("rs_score", 0.0)),
        )

        if latest_alert.get("catalyst_flags"):
            st.markdown(
                f"**Catalysts:** {', '.join(latest_alert.get('catalyst_flags', []))}"
            )

        if latest_alert.get("should_ding"):
            st.success("NEW SIGNAL TRIGGERED")

        with st.expander("Why this alert fired"):
            st.markdown("**Reasons**")
            for reason in latest_alert.get("reasons", []):
                st.write(f"- {reason}")

            if latest_alert.get("risks"):
                st.markdown("**Risks**")
                for risk in latest_alert.get("risks", []):
                    st.write(f"- {risk}")

            st.markdown("**Signal Memory**")
            st.write(f"- State: {latest_alert.get('signal_memory_state', 'unknown')}")
            st.write(f"- Persistence: {latest_alert.get('signal_persistence', 0)} cycles")
            st.write(f"- Confidence delta: {latest_alert.get('confidence_delta', 0.0)}")
            st.write(f"- Momentum delta: {latest_alert.get('momentum_delta', 0.0)}")
            st.write(f"- Volume delta: {latest_alert.get('volume_delta', 0.0)}")

            st.markdown("**Relative Strength**")
            st.write(f"- Sector ETF: {latest_alert.get('sector_etf', 'N/A')}")
            st.write(f"- RS score: {latest_alert.get('rs_score', 0.0)}")
            st.write(f"- Market label: {latest_alert.get('market_relative_label', 'unknown')}")
            st.write(f"- QQQ label: {latest_alert.get('qqq_relative_label', 'unknown')}")
            st.write(f"- Sector label: {latest_alert.get('sector_relative_label', 'unknown')}")
            st.write(f"- Summary: {latest_alert.get('relative_strength_summary', 'unknown')}")

            headlines = latest_alert.get("recent_headlines", [])
            if headlines:
                st.markdown("**Recent Headlines**")
                for headline in headlines[:5]:
                    title = headline.get("headline", "Untitled")
                    source = headline.get("source", "Unknown")
                    created_at = headline.get("created_at", "")
                    catalysts = headline.get("catalysts", [])
                    score = headline.get("sentiment_score", 0.0)

                    st.markdown(
                        f"- **{title}**  \n"
                        f"  Source: {source} | Score: {score:.2f} | "
                        f"Catalysts: {', '.join(catalysts) if catalysts else 'none'} | "
                        f"Time: {created_at}"
                    )
    else:
        message = latest_alert.get("message", "No active trading alert.") if latest_alert else "No active trading alert."
        st.info(message)


def render_performance_summary(summary: dict):
    st.divider()
    st.subheader("Signal Performance Summary")

    by_horizon = summary.get("by_horizon", {})
    horizon_keys = ["5", "15", "30", "60"]

    if by_horizon:
        horizon_cols = st.columns(len(horizon_keys))
        for i, horizon in enumerate(horizon_keys):
            stats = by_horizon.get(horizon, {})
            with horizon_cols[i]:
                st.markdown(f"**{horizon} Minute**")
                st.metric("Count", stats.get("count", 0))
                st.metric("Win Rate", stats.get("win_rate", 0.0))
                st.metric("Avg Return", stats.get("avg_return", 0.0))
                st.metric("Target Hit", stats.get("target_hit_rate", 0.0))
                st.metric("Stop Hit", stats.get("stop_hit_rate", 0.0))

    by_bucket = summary.get("by_confidence_bucket", {})
    if by_bucket:
        st.markdown("**Confidence Bucket Performance (15m)**")
        bucket_rows = []
        ordered_buckets = ["<0.60", "0.60-0.69", "0.70-0.79", "0.80-0.89", "0.90+"]
        for bucket in ordered_buckets:
            stats = by_bucket.get(bucket)
            if not stats:
                continue
            bucket_rows.append(
                {
                    "confidence_bucket": bucket,
                    "count": stats.get("count", 0),
                    "win_rate_15m": stats.get("win_rate_15m", 0.0),
                    "avg_return_15m": stats.get("avg_return_15m", 0.0),
                }
            )

        if bucket_rows:
            st.dataframe(pd.DataFrame(bucket_rows), use_container_width=True, hide_index=True)

    by_signal_type = summary.get("by_signal_type", {})
    if by_signal_type:
        st.markdown("**Signal Type Performance (15m)**")
        signal_type_rows = []
        for signal_type in ["BUY", "SELL"]:
            stats = by_signal_type.get(signal_type)
            if not stats:
                continue
            signal_type_rows.append(
                {
                    "signal_type": signal_type,
                    "count": stats.get("count", 0),
                    "win_rate_15m": stats.get("win_rate_15m", 0.0),
                    "avg_return_15m": stats.get("avg_return_15m", 0.0),
                }
            )

        if signal_type_rows:
            st.dataframe(pd.DataFrame(signal_type_rows), use_container_width=True, hide_index=True)


def render_recent_signal_log(recent_signal_log: list[dict]):
    st.divider()
    st.subheader("Recent Evaluated Signal Log")

    if not recent_signal_log:
        st.info("No evaluated signals logged yet.")
        return

    rows = []
    for record in recent_signal_log[:100]:
        outcome_5 = record.get("horizons", {}).get("5", {})
        outcome_15 = record.get("horizons", {}).get("15", {})
        outcome_30 = record.get("horizons", {}).get("30", {})
        outcome_60 = record.get("horizons", {}).get("60", {})

        rows.append(
            {
                "timestamp": record.get("timestamp"),
                "ticker": record.get("ticker"),
                "signal": record.get("signal"),
                "confidence": record.get("confidence"),
                "confidence_bucket": record.get("confidence_bucket"),
                "entry_price": record.get("entry_price"),
                "latest_price": record.get("latest_price"),
                "regime": record.get("regime"),
                "top_catalyst": record.get("top_catalyst"),
                "signal_memory_state": record.get("signal_memory_state"),
                "relative_strength_summary": record.get("relative_strength_summary"),
                "return_5m": outcome_5.get("return"),
                "return_15m": outcome_15.get("return"),
                "return_30m": outcome_30.get("return"),
                "return_60m": outcome_60.get("return"),
                "win_15m": outcome_15.get("win"),
                "target_hit_15m": outcome_15.get("target_hit"),
                "stop_hit_15m": outcome_15.get("stop_hit"),
                "max_favorable_return": record.get("max_favorable_return"),
                "max_adverse_return": record.get("max_adverse_return"),
            }
        )

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


st.title("Real-Time Trading Intelligence Engine")

heartbeat = store.get_json("worker_heartbeat", {})
signals = store.get_json("live_signals", [])
high_quality = store.get_json("high_quality_signals", [])
market_context = store.get_json("market_context", {})
latest_alert = store.get_json("latest_alert", {})
signal_performance_summary = store.get_json("signal_performance_summary", {})
recent_signal_log = store.get_json("recent_signal_log", [])

maybe_play_alert_sound(latest_alert)
render_latest_alert(latest_alert)

buy_signals = [
    item for item in signals
    if item.get("signal") == "BUY"
]

sell_signals = [
    item for item in signals
    if item.get("signal") == "SELL"
]

hold_signals = [
    item for item in signals
    if item.get("signal") == "HOLD"
]

top_cols = st.columns(8)

top_cols[0].metric("Worker", heartbeat.get("status", "unknown"))
top_cols[1].metric("Regime", market_context.get("regime", "unknown"))
top_cols[2].metric("Volatility", market_context.get("volatility_level", "unknown"))
top_cols[3].metric("Risk-On", market_context.get("risk_on_score", 0.0))
top_cols[4].metric("Signals", len(signals))
top_cols[5].metric("Buy Signals", len(buy_signals))
top_cols[6].metric("Sell Signals", len(sell_signals))
top_cols[7].metric("15m Win Rate", signal_performance_summary.get("by_horizon", {}).get("15", {}).get("win_rate", 0.0))

st.divider()

st.subheader("Primary Action Signal")

primary = None

if high_quality:
    primary = sorted(high_quality, key=lambda x: x.get("confidence", 0), reverse=True)[0]
elif buy_signals:
    primary = sorted(buy_signals, key=lambda x: x.get("confidence", 0), reverse=True)[0]
elif sell_signals:
    primary = sorted(sell_signals, key=lambda x: x.get("confidence", 0), reverse=True)[0]
elif hold_signals:
    primary = sorted(hold_signals, key=lambda x: x.get("confidence", 0), reverse=True)[0]

if primary:
    render_signal_card(primary, featured=True)
else:
    st.warning("No live signal available yet.")

st.divider()

left, middle, right = st.columns(3)

with left:
    st.subheader("Green Light — Buy Now")
    if buy_signals:
        for item in sorted(buy_signals, key=lambda x: x.get("confidence", 0), reverse=True):
            render_signal_card(item)
    else:
        st.info("No buy signals.")

with middle:
    st.subheader("Yellow Light — Hold / Watch")
    if hold_signals:
        for item in sorted(hold_signals, key=lambda x: x.get("confidence", 0), reverse=True)[:10]:
            render_signal_card(item)
    else:
        st.info("No hold signals.")

with right:
    st.subheader("Red Light — Sell / Avoid")
    if sell_signals:
        for item in sorted(sell_signals, key=lambda x: x.get("confidence", 0), reverse=True):
            render_signal_card(item)
    else:
        st.info("No sell signals.")

render_performance_summary(signal_performance_summary)
render_recent_signal_log(recent_signal_log)

st.divider()

st.subheader("Full Signal Table")

if signals:
    df = pd.DataFrame(signals)

    preferred_cols = [
        "ticker",
        "signal",
        "confidence",
        "long_confidence",
        "short_confidence",
        "price",
        "entry_zone",
        "stop",
        "target",
        "risk_reward",
        "regime",
        "volatility_level",
        "risk_on_score",
        "sentiment_label",
        "sentiment_score",
        "top_catalyst",
        "mention_spike",
        "article_count",
        "sector_etf",
        "rs_score",
        "market_relative_label",
        "sector_relative_label",
        "relative_strength_summary",
        "spread_pct",
        "volume_ratio",
        "momentum_5m",
        "momentum_15m",
        "momentum_acceleration",
        "signal_memory_state",
        "signal_persistence",
        "confidence_delta",
        "momentum_delta",
        "volume_delta",
        "vwap_state",
        "vwap_distance",
        "rsi",
        "adx",
        "signal_decay",
        "timestamp",
    ]

    preferred_cols = [col for col in preferred_cols if col in df.columns]

    st.dataframe(
        df[preferred_cols].sort_values("confidence", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.warning("No live signals yet. Make sure `signal_worker.py` is running.")
