"""Pydantic request/response models for the FastAPI backend."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# Users / tickets
# ---------------------------------------------------------------------------
class TicketCreate(_Base):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    subject: str = Field(min_length=2, max_length=300)
    message: str = Field(min_length=5, max_length=8000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Please provide a valid email address.")
        return value


class UserOut(_Base):
    id: str
    name: str
    email: str
    created_at: Optional[str] = None


class TicketOut(_Base):
    id: str
    user_id: str
    subject: str
    message: str
    category: Optional[str] = None
    confidence: Optional[float] = None
    status: str
    assigned_agent: Optional[str] = None
    resolution: Optional[str] = None
    priority: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TicketCreateResponse(_Base):
    ticket: TicketOut
    user: UserOut


class ProcessResponse(_Base):
    success: bool
    status: str
    ticket_id: str
    category: Optional[str] = None
    confidence: Optional[float] = None
    assigned_agent: Optional[str] = None
    resolution: Optional[str] = None
    customer_reply: str = ""
    sources: List[str] = Field(default_factory=list)
    escalation: Dict[str, Any] = Field(default_factory=dict)
    classification: Dict[str, Any] = Field(default_factory=dict)
    trace: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0
    error: Optional[str] = None
    retryable: bool = False


class ConversationMessage(_Base):
    id: str
    ticket_id: str
    user_id: Optional[str] = None
    role: str
    message: str
    created_at: Optional[str] = None


class MessageCreate(_Base):
    message: str = Field(min_length=1, max_length=8000)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
class AgentInfo(_Base):
    name: str
    description: str = ""
    responsibilities: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    status: str = "active"


class AgentLogOut(_Base):
    id: str
    ticket_id: Optional[str] = None
    agent_name: str
    action: str
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    execution_status: str
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------
class KnowledgeDocumentOut(_Base):
    title: str
    category: Optional[str] = None
    chunks: int = 0
    preview: str = ""
    embedded: bool = False
    created_at: Optional[str] = None


class IngestRequest(_Base):
    directory: Optional[str] = None
    replace: bool = True


class SearchRequest(_Base):
    query: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=4, ge=1, le=10)
    category: Optional[str] = None


class SearchResult(_Base):
    title: str
    content: str
    category: Optional[str] = None
    similarity: float = 0.0


class IngestResponse(_Base):
    state: str
    documents: int = 0
    chunks: int = 0
    errors: List[str] = Field(default_factory=list)
    titles: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Escalations
# ---------------------------------------------------------------------------
class VerdictRequest(_Base):
    verdict: str = Field(min_length=3, max_length=2000)
    resolution: str = Field(default="", max_length=4000)
    action: Literal["resolve", "reject", "reassign"] = "resolve"
    operator: str = Field(default="Human Support", max_length=120)


class EscalationOut(_Base):
    id: str
    ticket_id: str
    reason: str
    priority: str
    assigned_to: str
    status: str
    human_verdict: Optional[str] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None
    category: Optional[str] = None
    confidence: Optional[float] = None
    ticket_status: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None


# ---------------------------------------------------------------------------
# Dashboard / health
# ---------------------------------------------------------------------------
class DashboardStats(_Base):
    total: int = 0
    resolved: int = 0
    pending: int = 0
    escalated: int = 0
    failed: int = 0
    resolution_rate: float = 0.0
    category_distribution: List[Dict[str, Any]] = Field(default_factory=list)
    status_distribution: List[Dict[str, Any]] = Field(default_factory=list)
    recent_tickets: List[Dict[str, Any]] = Field(default_factory=list)
    agent_performance: List[Dict[str, Any]] = Field(default_factory=list)
    escalations: Dict[str, Any] = Field(default_factory=dict)


class HealthOut(_Base):
    status: str
    database_ok: bool
    database_message: str
    groq_configured: bool
    groq_model: str
    embedding_model: str
    app_env: str
    agents: int
