"""PAGE 4 - Agent Monitoring: roster, tool calls, traces and errors."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from frontend.utils import ApiError, api_get, empty_state, inject_css, page_header

inject_css()
page_header("Agent Monitoring", "The five agents, their tools, execution traces and errors.")

try:
    agents = api_get("/agents")
except ApiError as exc:
    st.error(str(exc))
    st.stop()

status_colors = {"active": "🟢", "degraded": "🟡", "error": "🔴"}
cols = st.columns(5)
for col, agent in zip(cols, agents):
    with col:
        st.markdown(
            f"### {status_colors.get(agent.get('status'), '⚪')} "
            f"{agent['name'].replace(' Specialist', '')}"
        )
        st.caption(agent.get("description", ""))
        st.markdown("**Tools**")
        for tool in agent.get("tools", []):
            st.markdown(f"- `{tool}`")
        with st.expander("Responsibilities"):
            for item in agent.get("responsibilities", []):
                st.markdown(f"- {item}")

st.divider()
tab1, tab2, tab3 = st.tabs(["Execution logs", "Performance", "Errors"])

try:
    logs = api_get("/agents/logs", params={"limit": 300})
except ApiError as exc:
    logs = []
    st.error(str(exc))

with tab1:
    if logs:
        agent_names = sorted({log["agent_name"] for log in logs})
        selected = st.multiselect("Filter by agent", agent_names, default=agent_names)
        filtered = [log for log in logs if log["agent_name"] in selected]
        df = pd.DataFrame(filtered)
        show_cols = [
            "created_at", "agent_name", "action", "execution_status",
            "duration_ms", "ticket_id", "error_message",
        ]
        st.dataframe(df[show_cols], use_container_width=True, hide_index=True)
        with st.expander("Inspect raw log entry"):
            index = st.selectbox("Log entry", range(len(filtered)), format_func=lambda i: (
                f"{filtered[i]['created_at']} · {filtered[i]['agent_name']} · {filtered[i]['action']}"
            ))
            st.json(filtered[index])
    else:
        empty_state("No agent executions logged yet.")

with tab2:
    if logs:
        df = pd.DataFrame(logs)
        by_agent = (
            df.groupby("agent_name")
            .agg(runs=("id", "count"), errors=("execution_status", lambda s: (s == "error").sum()),
                 avg_ms=("duration_ms", "mean"))
            .reset_index()
        )
        fig = px.bar(
            by_agent, x="agent_name", y="runs", color="errors",
            color_continuous_scale=["#bbf7d0", "#ef4444"],
        )
        fig.update_layout(
            height=340, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="", yaxis_title="Executions",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(by_agent, use_container_width=True, hide_index=True)
    else:
        empty_state("Run a ticket to see agent performance.")

with tab3:
    errors = [log for log in logs if log.get("execution_status") == "error"]
    if errors:
        st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)
    else:
        empty_state("No errors recorded - all agent executions succeeded.")
