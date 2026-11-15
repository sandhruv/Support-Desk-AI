"""PAGE 3 - Ticket Management: browse, filter and inspect every ticket."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from frontend.utils import (
    ApiError,
    api_get,
    api_post,
    conversation_bubbles,
    empty_state,
    inject_css,
    page_header,
)

inject_css()
page_header("Ticket Management", "Search and inspect tickets, agent decisions and full conversations.")

filters = st.columns(4)
category = filters[0].selectbox("Category", ["All", "billing", "technical", "account", "other"])
status_filter = filters[1].selectbox(
    "Status", ["All", "open", "processing", "pending", "resolved", "escalated", "failed"]
)
priority = filters[2].selectbox("Priority", ["All", "low", "medium", "high", "urgent"])
search = filters[3].text_input("Search subject/message", placeholder="refund, TXN1001...")

params = {"limit": 300}
if category != "All":
    params["category"] = category
if status_filter != "All":
    params["status"] = status_filter
if priority != "All":
    params["priority"] = priority
if search.strip():
    params["search"] = search.strip()

try:
    tickets = api_get("/tickets", params=params)
except ApiError as exc:
    st.error(str(exc))
    st.stop()

if not tickets:
    empty_state("No tickets match these filters.")
    st.stop()

df = pd.DataFrame(tickets)
display_cols = [
    "id", "subject", "category", "confidence", "status",
    "priority", "assigned_agent", "created_at",
]
st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
st.caption(f"{len(tickets)} ticket(s)")

st.divider()
selected = st.selectbox(
    "Open ticket",
    options=[t["id"] for t in tickets],
    format_func=lambda tid: next(
        (f"{t['subject']} · {t['status']} · {tid[:8]}" for t in tickets if t["id"] == tid),
        tid,
    ),
)

if selected:
    ticket = next(t for t in tickets if t["id"] == selected)
    left, right = st.columns((1, 1))

    with left:
        st.subheader(ticket["subject"])
        confidence_value = (
            f"{ticket['confidence']:.0%}" if ticket.get("confidence") is not None else "-"
        )
        st.markdown(
            f"**Customer message**\n\n> {ticket['message']}\n\n"
            f"**Category:** {ticket.get('category') or '-'} · "
            f"**Confidence:** {confidence_value} · "
            f"**Priority:** {ticket.get('priority')}\n\n"
            f"**Status:** {ticket.get('status')} · "
            f"**Agent:** {ticket.get('assigned_agent') or '-'}"
        )
        if ticket.get("resolution"):
            st.info(ticket["resolution"])
        if st.button("Re-process with agents", use_container_width=True):
            try:
                with st.spinner("Running multi-agent pipeline..."):
                    result = api_post(f"/tickets/{selected}/process")
                st.success(f"Status: {result.get('status')} · {result.get('duration_ms')} ms")
                st.json(result.get("trace", []))
            except ApiError as exc:
                st.error(str(exc))

    with right:
        st.subheader("Conversation history")
        try:
            history = api_get(f"/tickets/{selected}/conversation")
            conversation_bubbles(history)
        except ApiError as exc:
            st.error(str(exc))

    with st.expander("Agent logs for this ticket"):
        try:
            logs = api_get("/agents/logs", params={"ticket_id": selected, "limit": 100})
            if logs:
                st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
            else:
                st.caption("No logs for this ticket yet.")
        except ApiError as exc:
            st.error(str(exc))
