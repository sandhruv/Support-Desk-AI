"""PAGE 6 - Human Escalation: human-in-the-loop review and verdicts."""

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
page_header(
    "Human Escalation",
    "Review low-confidence or unresolved tickets, inspect agent findings and issue a verdict.",
)

status_filter = st.selectbox("Queue", ["pending", "in_review", "resolved", "rejected", "reassigned", "all"])
try:
    escalations = api_get(
        "/escalations",
        params={"status": None if status_filter == "all" else status_filter, "limit": 200},
    )
except ApiError as exc:
    st.error(str(exc))
    st.stop()

if not escalations:
    empty_state("No escalations in this queue.")
    st.stop()

df = pd.DataFrame(escalations)
st.dataframe(
    df[["id", "subject", "customer_name", "priority", "status", "created_at"]],
    use_container_width=True,
    hide_index=True,
)

selected_id = st.selectbox(
    "Select escalation",
    options=[row["id"] for row in escalations],
    format_func=lambda eid: next(
        (
            f"{row['priority'].upper()} · {row.get('subject', '')[:50]} · "
            f"{row.get('customer_name', '')} · {row['status']}"
            for row in escalations
            if row["id"] == eid
        ),
        eid,
    ),
)
escalation = next(row for row in escalations if row["id"] == selected_id)

left, right = st.columns((1, 1))

with left:
    st.subheader(escalation.get("subject", "Escalated ticket"))
    st.markdown(
        f"**Customer:** {escalation.get('customer_name')} "
        f"({escalation.get('customer_email')})\n\n"
        f"**Original message**\n\n> {escalation.get('message', '')}\n\n"
        f"**Category:** {escalation.get('category') or '-'} · "
        f"**Confidence:** {escalation.get('confidence') or 0:.0%} · "
        f"**Priority:** {escalation.get('priority')}\n\n"
        f"**Escalation reason:** {escalation.get('reason', '')}"
    )
    if escalation.get("human_verdict"):
        st.success(f"Human verdict: {escalation['human_verdict']}")

    st.subheader("Conversation history")
    try:
        history = api_get(f"/tickets/{escalation['ticket_id']}/conversation")
        conversation_bubbles(history)
    except ApiError as exc:
        st.error(str(exc))

with right:
    st.subheader("Agent findings")
    try:
        logs = api_get(
            "/agents/logs", params={"ticket_id": escalation["ticket_id"], "limit": 100}
        )
        if logs:
            for log in logs[:20]:
                st.markdown(
                    f"**{log['agent_name']}** · `{log['action']}` · "
                    f"{log['execution_status']} · {log.get('duration_ms') or 0} ms"
                )
                st.caption(str(log.get("output_data"))[:400])
        else:
            st.caption("No agent logs found for this ticket.")
    except ApiError as exc:
        st.error(str(exc))

    st.subheader("Human verdict")
    with st.form("verdict_form"):
        verdict = st.text_area(
            "Verdict / findings",
            height=110,
            placeholder="Verified duplicate charge for TXN1001 in the payment dashboard. Refund approved per policy.",
        )
        resolution = st.text_area(
            "Resolution shared with the customer",
            height=90,
            placeholder="Your refund has been approved and will appear in 5-7 business days.",
        )
        action = st.selectbox(
            "Action",
            ["resolve", "reject", "reassign"],
            help="resolve = close ticket, reject = reopen for AI retry, reassign = keep with human team",
        )
        operator = st.text_input("Operator name", value="Human Support")
        submitted = st.form_submit_button("Submit verdict", use_container_width=True)

    if submitted:
        if not verdict.strip():
            st.warning("A verdict is required.")
        else:
            try:
                result = api_post(
                    f"/escalations/{selected_id}/verdict",
                    {
                        "verdict": verdict.strip(),
                        "resolution": resolution.strip(),
                        "action": action,
                        "operator": operator.strip() or "Human Support",
                    },
                )
                st.success(
                    f"Verdict saved. Ticket status: {result.get('ticket_status')}"
                )
                st.rerun()
            except ApiError as exc:
                st.error(str(exc))
