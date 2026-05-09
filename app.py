import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from redis_store import store


st.set_page_config(
    page_title="Trading Intelligence Engine",
    layout="wide",
)

st_autorefresh(interval=30_000, key="refresh")

st.title("Real-Time Trading Intelligence Engine")

heartbeat = store.get_json("worker_heartbeat", {})
signals = store.get_json("live_signals", [])
high_quality = store.get_json("high_quality_signals", [])
market_context = store.get_json("market_context", {})

top_cols = st.columns(4)

top_cols[0].metric("Worker", heartbeat.get("status", "unknown"))
top_cols[1].metric("Signals", len(signals))
top_cols[2].metric("High Quality", len(high_quality))
top_cols[3].metric("Regime", market_context.get("regime", "unknown"))

st.divider()

st.subheader("High-Quality Setups")

if high_quality:
    for item in high_quality:
        with st.container(border=True):
            cols = st.columns([1, 1, 1, 1, 1])
            cols[0].markdown(f"### {item['ticker']}")
            cols[1].metric("Signal", item["signal"])
            cols[2].metric("Confidence", f"{item['confidence']:.2f}")
            cols[3].metric("Price", item["price"])
            cols[4].metric("R/R", item["risk_reward"])

            st.markdown("**Reason**")
            for reason in item.get("reasons", []):
                st.write(f"- {reason}")

            if item.get("risks"):
                st.markdown("**Risk**")
                for risk in item.get("risks", []):
                    st.write(f"- {risk}")

            risk_cols = st.columns(3)
            risk_cols[0].metric("Entry", item.get("entry_zone"))
            risk_cols[1].metric("Stop", item.get("stop"))
            risk_cols[2].metric("Target", item.get("target"))
else:
    st.info("No high-quality setups right now.")

st.divider()

st.subheader("Live Signals Feed")

if signals:
    df = pd.DataFrame(signals)
    st.dataframe(
        df[
            [
                "ticker",
                "signal",
                "confidence",
                "price",
                "volume_ratio",
                "momentum_15m",
                "vwap_distance",
                "risk_reward",
                "regime",
                "timestamp",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.warning("No live signals yet. Make sure `signal_worker.py` is running.")
