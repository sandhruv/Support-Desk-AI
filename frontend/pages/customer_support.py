"""PAGE 2 - Customer Support: submit complaints and watch the agents work."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    "Customer Support",
    "Submit a complaint. The Classifier routes it to the right specialist agent automatically.",
)

result_key = "last_process_result"


def render_result(result: dict) -> None:
    st.divider()
    st.subheader("Resolution")
    status = result.get("status", "unknown")
    cols = st.columns(4)
    cols[0].metric("Status", status.capitalize())
    cols[1].metric("Category", (result.get("category") or "-").capitalize())
    confidence = result.get("confidence")
    cols[2].metric("Confidence", f"{confidence:.0%}" if confidence is not None else "-")
    cols[3].metric("Assigned agent", result.get("assigned_agent") or "-")

    classification = result.get("classification") or {}
    output = classification.get("output") or {}
    if output.get("issue"):
        st.markdown(f"**Detected issue:** {output['issue']}")
    if output.get("reasoning"):
        st.markdown(f"**Agent reasoning:** {output['reasoning']}")

    if result.get("customer_reply"):
        st.success(result["customer_reply"])
    elif result.get("error"):
        st.error(result["error"])

    sources = result.get("sources") or []
    if sources:
        st.markdown("**Knowledge sources used:** " + ", ".join(f"`{s}`" for s in sources))

    escalation = result.get("escalation") or {}
    if escalation:
        st.warning(
            f"Escalated to **{escalation.get('assigned_to', 'Human Support Queue')}** "
            f"(priority: {escalation.get('priority', 'high')})."
        )

    if result.get("trace"):
        with st.expander("Execution trace (agent handoffs)"):
            for step in result["trace"]:
                st.markdown(
                    f"- **{step.get('agent')}** · {step.get('action')} "
                    f"{'— ' + step['detail'] if step.get('detail') else ''}"
                )
    if result.get("errors"):
        with st.expander("Errors"):
            st.json(result["errors"])
    if result.get("ticket_id"):
        st.caption(f"Ticket ID: `{result['ticket_id']}` · took {result.get('duration_ms', 0)} ms")


left, right = st.columns((1.1, 1))

with left:
    st.subheader("New complaint")
    with st.form("ticket_form", clear_on_submit=False):
        name = st.text_input("Customer name", placeholder="Aarav Sharma")
        email = st.text_input("Email", placeholder="aarav@example.com")
        subject = st.text_input("Subject", placeholder="My payment was deducted twice")
        priority = st.selectbox("Priority", ["low", "medium", "high", "urgent"], index=1)
        message = st.text_area(
            "Complaint",
            height=150,
            placeholder="Describe the problem in detail. Include transaction references (e.g. TXN1001) when relevant.",
        )
        submitted = st.form_submit_button("Submit to AI support", use_container_width=True)

    if submitted:
        if not all([name.strip(), email.strip(), subject.strip(), message.strip()]):
            st.warning("Please fill in every field.")
        else:
            try:
                with st.spinner("Creating ticket..."):
                    created = api_post(
                        "/tickets",
                        {
                            "name": name.strip(),
                            "email": email.strip(),
                            "subject": subject.strip(),
                            "message": message.strip(),
                            "priority": priority,
                        },
                    )
                ticket_id = created["ticket"]["id"]
                with st.spinner("Classifier → specialist → resolution..."):
                    result = api_post(f"/tickets/{ticket_id}/process")
                st.session_state[result_key] = result
                st.session_state["active_ticket_id"] = ticket_id
                st.success(f"Ticket {ticket_id[:8]} created and processed.")
            except ApiError as exc:
                st.error(str(exc))

with right:
    st.subheader("Conversation")
    ticket_id_input = st.text_input(
        "Ticket ID",
        value=st.session_state.get("active_ticket_id", ""),
        placeholder="Paste a ticket UUID",
    )
    if st.button("Load conversation", use_container_width=True):
        if ticket_id_input.strip():
            try:
                history = api_get(f"/tickets/{ticket_id_input.strip()}/conversation")
                st.session_state["loaded_conversation"] = history
            except ApiError as exc:
                st.error(str(exc))
        else:
            st.warning("Enter a ticket ID.")

    history = st.session_state.get("loaded_conversation")
    if history:
        conversation_bubbles(history)
    elif not st.session_state.get(result_key):
        empty_state("Submit a complaint or load an existing ticket to see its conversation.")

    with st.expander("Follow-up message (shared memory demo)"):
        st.caption(
            "Example: first message 'My payment failed.', then follow up with 'TXN1001'. "
            "The Billing Specialist recovers the reference from conversation memory."
        )
        followup = st.text_area("Follow-up", height=80, placeholder="TXN1001")
        if st.button("Send follow-up & reprocess"):
            tid = (ticket_id_input or st.session_state.get("active_ticket_id", "")).strip()
            if not tid or not followup.strip():
                st.warning("Provide a ticket ID and a follow-up message.")
            else:
                try:
                    api_post(f"/tickets/{tid}/messages", {"message": followup.strip()})
                    with st.spinner("Agents are re-processing with full history..."):
                        result = api_post(f"/tickets/{tid}/process")
                    st.session_state[result_key] = result
                    st.session_state["loaded_conversation"] = api_get(
                        f"/tickets/{tid}/conversation"
                    )
                    st.success("Follow-up processed.")
                except ApiError as exc:
                    st.error(str(exc))

result = st.session_state.get(result_key)
if result:
    render_result(result)
