"""Enterprise Customer Support AI - Streamlit dashboard entry point.

Run with:  python run.py ui    (or: streamlit run frontend/app.py)
The frontend talks ONLY to the FastAPI backend (no direct Supabase access).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from frontend.utils import inject_css, health_pill

st.set_page_config(
    page_title="Support Desk AI | CSE476",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

st.sidebar.markdown("## Support Desk AI")
st.sidebar.caption("CSE476 · Agentic AI & Intelligent Automation")
st.sidebar.divider()

navigation = st.navigation(
    {
        "Operations": [
            st.Page("pages/overview.py", title="Overview", icon=":material/dashboard:"),
            st.Page("pages/customer_support.py", title="Customer Support", icon=":material/support_agent:"),
            st.Page("pages/ticket_management.py", title="Ticket Management", icon=":material/confirmation_number:"),
        ],
        "Intelligence": [
            st.Page("pages/agent_monitoring.py", title="Agent Monitoring", icon=":material/monitoring:"),
            st.Page("pages/knowledge_base.py", title="Knowledge Base", icon=":material/library_books:"),
        ],
        "Human Loop": [
            st.Page("pages/human_escalation.py", title="Human Escalation", icon=":material/escalator_warning:"),
        ],
    }
)

health_pill()
st.sidebar.divider()
st.sidebar.caption(
    "Multi-agent pipeline: Classifier → Billing / Technical / Account "
    "→ Escalation Router → Human Support."
)

navigation.run()
