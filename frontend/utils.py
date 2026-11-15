"""Shared Streamlit helpers: API client, styling and small UI widgets.

The Streamlit frontend NEVER touches Supabase directly - all operations go
through the FastAPI backend, which keeps credentials server-side.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import requests
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:  # pragma: no cover
    pass

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = 60


class ApiError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _handle(response: requests.Response) -> Any:
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        if isinstance(detail, dict):
            detail = detail.get("message", str(detail))
        raise ApiError(str(detail))
    if not response.content:
        return None
    return response.json()


def api_get(path: str, params: Optional[dict] = None) -> Any:
    try:
        return _handle(requests.get(f"{API_BASE_URL}{path}", params=params, timeout=REQUEST_TIMEOUT))
    except requests.ConnectionError as exc:
        raise ApiError(
            f"Cannot reach the FastAPI backend at {API_BASE_URL}. "
            "Start it with: python run.py api"
        ) from exc


def api_post(path: str, json: Optional[dict] = None, params: Optional[dict] = None) -> Any:
    try:
        return _handle(
            requests.post(
                f"{API_BASE_URL}{path}", json=json, params=params, timeout=REQUEST_TIMEOUT
            )
        )
    except requests.ConnectionError as exc:
        raise ApiError(
            f"Cannot reach the FastAPI backend at {API_BASE_URL}. "
            "Start it with: python run.py api"
        ) from exc


def api_upload(path: str, filename: str, content: bytes, category: Optional[str] = None) -> Any:
    files = {"file": (filename, content)}
    params = {"category": category} if category else None
    try:
        return _handle(
            requests.post(
                f"{API_BASE_URL}{path}", files=files, params=params, timeout=300
            )
        )
    except requests.ConnectionError as exc:
        raise ApiError(f"Cannot reach the FastAPI backend at {API_BASE_URL}.") from exc


def api_delete(path: str) -> Any:
    try:
        return _handle(requests.delete(f"{API_BASE_URL}{path}", timeout=REQUEST_TIMEOUT))
    except requests.ConnectionError as exc:
        raise ApiError(f"Cannot reach the FastAPI backend at {API_BASE_URL}.") from exc


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
#MainMenu, footer, header {visibility: hidden;}

.stApp { background: #f6f8fb; }
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    border-right: 1px solid #243244;
}
section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
section[data-testid="stSidebar"] a { border-radius: 8px; }
section[data-testid="stSidebar"] a:hover { background: rgba(255,255,255,0.08); }
section[data-testid="stSidebar"] a[aria-current="page"] {
    background: #2563eb !important; color: white !important; font-weight: 600;
}

.page-title { font-size: 1.9rem; font-weight: 700; color: #0f172a; margin-bottom: 0.15rem; letter-spacing: -0.02em; }
.page-subtitle { color: #64748b; font-size: 0.95rem; margin-bottom: 1.4rem; }

.metric-card {
    background: white; border: 1px solid #e2e8f0; border-radius: 14px;
    padding: 1rem 1.2rem; box-shadow: 0 1px 2px rgba(15,23,42,0.04);
    height: 100%;
}
.metric-label { color: #64748b; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
.metric-value { color: #0f172a; font-size: 1.75rem; font-weight: 700; margin-top: 0.2rem; }
.metric-hint { color: #94a3b8; font-size: 0.75rem; margin-top: 0.15rem; }

.card {
    background: white; border: 1px solid #e2e8f0; border-radius: 14px;
    padding: 1.2rem 1.4rem; margin-bottom: 1rem;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
}
.card h4 { margin: 0 0 0.4rem 0; color: #0f172a; font-size: 1rem; }
.card p { margin: 0.15rem 0; color: #475569; font-size: 0.9rem; }

.badge { display: inline-block; padding: 0.18rem 0.6rem; border-radius: 999px;
         font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
.badge-resolved { background: #dcfce7; color: #166534; }
.badge-open, .badge-processing { background: #dbeafe; color: #1e40af; }
.badge-escalated { background: #fee2e2; color: #991b1b; }
.badge-pending { background: #fef3c7; color: #92400e; }
.badge-failed { background: #f3e8ff; color: #6b21a8; }
.badge-other { background: #e2e8f0; color: #334155; }

.bubble { border-radius: 12px; padding: 0.75rem 1rem; margin: 0.35rem 0; font-size: 0.9rem; }
.bubble-customer { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e3a8a; }
.bubble-assistant { background: #f8fafc; border: 1px solid #e2e8f0; color: #334155; }
.bubble-human_support { background: #f0fdf4; border: 1px solid #bbf7d0; color: #14532d; }
.bubble-role { font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; }

.stButton > button {
    background: #2563eb; color: white; border: 0; border-radius: 9px;
    padding: 0.5rem 1.2rem; font-weight: 600;
}
.stButton > button:hover { background: #1d4ed8; color: white; }
.stDownloadButton > button { border-radius: 9px; }

div[data-testid="stExpander"] { background: white; border: 1px solid #e2e8f0; border-radius: 12px; }
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
    border-radius: 9px !important;
}
.empty-state {
    text-align: center; color: #64748b; background: white;
    border: 1px dashed #cbd5e1; border-radius: 14px; padding: 2.4rem 1rem; font-size: 0.92rem;
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def metric_card(label: str, value: Any, hint: str = "") -> str:
    return (
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'<div class="metric-hint">{hint}</div></div>'
    )


def badge(status: str) -> str:
    status = (status or "other").lower().replace(" ", "_")
    css = {
        "resolved": "badge-resolved",
        "open": "badge-open",
        "processing": "badge-processing",
        "escalated": "badge-escalated",
        "pending": "badge-pending",
        "failed": "badge-failed",
    }.get(status, "badge-other")
    return f'<span class="badge {css}">{status.replace("_", " ")}</span>'


def empty_state(message: str) -> None:
    st.markdown(f'<div class="empty-state">{message}</div>', unsafe_allow_html=True)


def show_error(exc: Exception) -> None:
    st.error(str(exc))


def conversation_bubbles(history: list[dict]) -> None:
    if not history:
        empty_state("No conversation history yet.")
        return
    for msg in history:
        role = msg.get("role", "assistant")
        css = {
            "customer": "bubble-customer",
            "assistant": "bubble-assistant",
            "human_support": "bubble-human_support",
        }.get(role, "bubble-assistant")
        label = {
            "customer": "Customer",
            "assistant": "AI Assistant",
            "human_support": "Human Support",
            "system": "System",
        }.get(role, role)
        st.markdown(
            f'<div class="bubble {css}"><div class="bubble-role">{label}</div>'
            f'{msg.get("message", "")}</div>',
            unsafe_allow_html=True,
        )


def health_pill() -> None:
    try:
        health = api_get("/health")
        db = "DB connected" if health.get("database_ok") else "DB not configured"
        groq = "Groq ready" if health.get("groq_configured") else "Groq key missing"
        st.sidebar.caption(f"API: {API_BASE_URL}")
        st.sidebar.caption(f"{db} · {groq}")
    except ApiError:
        st.sidebar.caption("API offline - start with `python run.py api`")
