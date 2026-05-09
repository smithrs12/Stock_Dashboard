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

    render_sentiment_chip(
        item.get("sentiment_label", "neutral"),
        float(item.get("sentiment_score", 0.0)),
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

        render_sentiment_chip(
            latest_alert.get("sentiment_label", "neutral"),
            float(latest_alert.get("sentiment_score", 0.0)),
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


st.title("Real-Time Trading Intelligence Engine")

heartbeat = store.get_json("worker_heartbeat", {})
signals = store.get_json("live_signals", [])
high_quality = store.get_json("high_quality_signals", [])
market_context = store.get_json("market_context", {})
latest_alert = store.get_json("latest_alert", {})

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

top_cols = st.columns(7)

top_cols[0].metric("Worker", heartbeat.get("status", "unknown"))
top_cols[1].metric("Regime", market_context.get("regime", "unknown"))
top_cols[2].metric("Volatility", market_context.get("volatility_level", "unknown"))
top_cols[3].metric("Risk-On", market_context.get("risk_on_score", 0.0))
top_cols[4].metric("Signals", len(signals))
top_cols[5].metric("Buy Signals", len(buy_signals))
top_cols[6].metric("Sell Signals", len(sell_signals))

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
        "spread_pct",
        "volume_ratio",
        "momentum_5m",
        "momentum_15m",
        "momentum_acceleration",
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
