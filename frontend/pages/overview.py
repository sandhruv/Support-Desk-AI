"""PAGE 1 - Overview dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from frontend.utils import (
    ApiError,
    api_get,
    badge,
    empty_state,
    inject_css,
    metric_card,
    page_header,
)

inject_css()
page_header(
    "Operations Overview",
    "Live health of the multi-agent support desk: volume, resolution and agent activity.",
)

try:
    stats = api_get("/dashboard/stats")
except ApiError as exc:
    st.error(str(exc))
    st.info("Configure Supabase (.env → DATABASE_URL) and run the SQL migrations, then retry.")
    st.stop()

total = stats.get("total", 0)
resolved = stats.get("resolved", 0)
pending = stats.get("pending", 0)
escalated = stats.get("escalated", 0)
rate = stats.get("resolution_rate", 0.0)

cols = st.columns(5)
cols[0].markdown(metric_card("Total tickets", total), unsafe_allow_html=True)
cols[1].markdown(metric_card("Resolved", resolved), unsafe_allow_html=True)
cols[2].markdown(metric_card("Pending", pending), unsafe_allow_html=True)
cols[3].markdown(metric_card("Escalated", escalated), unsafe_allow_html=True)
cols[4].markdown(metric_card("Resolution rate", f"{rate:.0%}", "resolved / total"), unsafe_allow_html=True)

st.write("")

left, right = st.columns((1, 1))

with left:
    st.subheader("Category distribution")
    categories = stats.get("category_distribution", [])
    if categories:
        df = pd.DataFrame(categories)
        fig = px.pie(
            df, names="category", values="count", hole=0.55,
            color_discrete_sequence=["#2563eb", "#0ea5e9", "#22c55e", "#f59e0b", "#94a3b8"],
        )
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=10), height=320,
            paper_bgcolor="rgba(0,0,0,0)", legend_title_text="",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        empty_state("No tickets yet - submit one from Customer Support.")

with right:
    st.subheader("Status distribution")
    statuses = stats.get("status_distribution", [])
    if statuses:
        df = pd.DataFrame(statuses)
        fig = px.bar(
            df, x="status", y="count", color="status",
            color_discrete_map={
                "resolved": "#22c55e", "open": "#3b82f6", "processing": "#6366f1",
                "escalated": "#ef4444", "pending": "#f59e0b", "failed": "#a855f7",
            },
        )
        fig.update_layout(
            showlegend=False, height=320, margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="", yaxis_title="Tickets",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        empty_state("No ticket status data yet.")

st.divider()
left, right = st.columns((1.4, 1))

with left:
    st.subheader("Recent activity")
    recent = stats.get("recent_tickets", [])
    if recent:
        df = pd.DataFrame(recent)
        df["status"] = df["status"].map(lambda s: s.capitalize())
        st.dataframe(
            df[["subject", "category", "status", "priority", "assigned_agent", "created_at"]],
            use_container_width=True, hide_index=True,
        )
    else:
        empty_state("No recent tickets.")

with right:
    st.subheader("Agent performance")
    performance = stats.get("agent_performance", [])
    if performance:
        df = pd.DataFrame(performance)
        df["agent_name"] = df["agent_name"].str.replace(" Specialist", "", regex=False)
        fig = px.bar(
            df, x="runs", y="agent_name", orientation="h", color="errors",
            color_continuous_scale=["#bbf7d0", "#ef4444"],
        )
        fig.update_layout(
            height=300, margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis_title="", xaxis_title="Executions",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        empty_state("Agents have not run yet.")

st.divider()
st.subheader("Escalation queue")
esc = stats.get("escalations", {})
c1, c2 = st.columns(2)
c1.markdown(metric_card("Total escalations", esc.get("total", 0)), unsafe_allow_html=True)
c2.markdown(metric_card("Pending human review", esc.get("pending", 0)), unsafe_allow_html=True)
if esc.get("pending", 0):
    st.warning("Escalated tickets are waiting for a human verdict. Open **Human Escalation**.")
else:
    st.success("No escalations waiting for human review.")
