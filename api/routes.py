"""FastAPI routes for the CSE476 Customer Support AI system."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from api.deps import get_services
from api.schemas import (
    AgentInfo,
    AgentLogOut,
    ConversationMessage,
    DashboardStats,
    EscalationOut,
    HealthOut,
    IngestRequest,
    IngestResponse,
    KnowledgeDocumentOut,
    MessageCreate,
    ProcessResponse,
    SearchRequest,
    SearchResult,
    TicketCreate,
    TicketCreateResponse,
    TicketOut,
    UserOut,
    VerdictRequest,
)
from database.connection import (
    DatabaseNotConfiguredError,
    check_database_connection,
)
from llm.groq_client import GroqNotConfiguredError, GroqServiceError
from llm.model_config import AGENT_HUMAN, validate_configuration
from orchestration.coordinator import TicketNotFoundError
from rag.document_loader import SUPPORTED_EXTENSIONS

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "knowledge_base" / "uploads"


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            f"Database unavailable: {exc}. Configure DATABASE_URL in .env "
            "(see .env.example) and run the SQL migrations."
        ),
    )


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------
@router.post("/tickets", response_model=TicketCreateResponse, status_code=201, tags=["tickets"])
def create_ticket(payload: TicketCreate):
    """Create a customer, a ticket and the first conversation message."""
    services = get_services()
    try:
        user = services.repository.get_or_create_user(payload.name, payload.email)
        ticket = services.repository.create_ticket(
            user_id=user["id"],
            subject=payload.subject,
            message=payload.message,
            priority=payload.priority,
        )
        services.memory.add_customer_message(
            ticket_id=ticket["id"],
            message=payload.message,
            user_id=user["id"],
        )
        services.repository.log_agent(
            ticket_id=ticket["id"],
            agent_name="Support Coordinator",
            action="ticket_created",
            input_data={"subject": payload.subject, "priority": payload.priority},
            output_data={"ticket_id": ticket["id"]},
        )
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create ticket: {exc}") from exc
    return TicketCreateResponse(ticket=TicketOut(**ticket), user=UserOut(**user))


@router.get("/tickets", response_model=list[TicketOut], tags=["tickets"])
def list_tickets(
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
):
    try:
        return get_services().repository.list_tickets(
            category=category,
            status=status_filter,
            priority=priority,
            search=search,
            limit=limit,
        )
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc


@router.get("/tickets/{ticket_id}", response_model=TicketOut, tags=["tickets"])
def get_ticket(ticket_id: str):
    try:
        ticket = get_services().repository.get_ticket(ticket_id)
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post(
    "/tickets/{ticket_id}/process",
    response_model=ProcessResponse,
    tags=["tickets"],
)
async def process_ticket(ticket_id: str):
    """Run the full multi-agent pipeline (classify -> specialist -> resolve/escalate)."""
    services = get_services()
    try:
        result = await services.coordinator.process_ticket(ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc
    except (GroqNotConfiguredError, GroqServiceError) as exc:
        # Ticket preserved for retry - rate limits / outages are recoverable.
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "ticket_preserved": True,
                "retryable": getattr(exc, "retryable", True),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": f"Processing failed: {exc}", "ticket_preserved": True},
        ) from exc
    return result


@router.get(
    "/tickets/{ticket_id}/conversation",
    response_model=list[ConversationMessage],
    tags=["tickets"],
)
def get_conversation(ticket_id: str):
    try:
        return get_services().repository.get_conversation(ticket_id)
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=ConversationMessage,
    status_code=201,
    tags=["tickets"],
)
def add_customer_message(ticket_id: str, payload: MessageCreate):
    """Save a follow-up customer message (persistent shared memory)."""
    services = get_services()
    try:
        ticket = services.repository.get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return services.memory.add_customer_message(
            ticket_id=ticket_id,
            message=payload.message,
            user_id=ticket.get("user_id"),
        )
    except HTTPException:
        raise
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
@router.get("/agents", response_model=list[AgentInfo], tags=["agents"])
def list_agents():
    try:
        services = get_services()
        roster = services.coordinator.get_agent_roster()
        # Agent health reflects the LATEST run, not historical lifetime errors.
        latest_run_status: dict[str, str] = {}
        for log in services.repository.list_agent_logs(limit=300):
            name = log.get("agent_name")
            if name in latest_run_status:
                continue
            if log.get("action") == "run":
                latest_run_status[name] = log.get("execution_status") or ""
        for agent in roster:
            latest = latest_run_status.get(agent["name"])
            if latest == "error":
                agent["status"] = "error"
            elif latest == "success":
                agent["status"] = "active"
        return roster
    except DatabaseNotConfiguredError:
        # Roster is static information; return it without DB stats.
        return get_services().coordinator.get_agent_roster()
    except Exception:
        return get_services().coordinator.get_agent_roster()


@router.get("/agents/logs", response_model=list[AgentLogOut], tags=["agents"])
def agent_logs(
    ticket_id: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
):
    try:
        return get_services().repository.list_agent_logs(
            ticket_id=ticket_id, agent_name=agent_name, limit=limit
        )
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# Knowledge base (RAG)
# ---------------------------------------------------------------------------
@router.get("/knowledge", response_model=list[KnowledgeDocumentOut], tags=["knowledge"])
def list_knowledge():
    try:
        return get_services().repository.list_knowledge()
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc


@router.post("/knowledge/upload", response_model=IngestResponse, tags=["knowledge"])
async def upload_knowledge(
    file: UploadFile = File(...),
    category: str | None = None,
):
    """Upload a TXT/MD/JSON/PDF document and index it into pgvector."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / Path(file.filename).name
    services = get_services()
    try:
        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = services.ingestion.ingest_file(destination, category=category)
        if result.get("errors"):
            raise HTTPException(status_code=500, detail=result["errors"])
        return result
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Upload/indexing failed: {exc}"
        ) from exc
    finally:
        file.file.close()


@router.post("/knowledge/ingest", response_model=IngestResponse, tags=["knowledge"])
def ingest_knowledge(payload: IngestRequest):
    """Index the built-in knowledge_base directory (or a custom directory)."""
    services = get_services()
    try:
        return services.ingestion.ingest_directory(
            payload.directory, replace=payload.replace
        )
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc


@router.post("/knowledge/search", response_model=list[SearchResult], tags=["knowledge"])
def search_knowledge(payload: SearchRequest):
    """Test semantic search (pgvector) without generating an LLM answer."""
    try:
        results = get_services().retriever.retrieve(
            payload.query, top_k=payload.top_k, category=payload.category
        )
        return [
            {
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "category": item.get("category"),
                "similarity": item.get("similarity", 0.0),
            }
            for item in results
        ]
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc


@router.delete("/knowledge/{title}", tags=["knowledge"])
def delete_knowledge(title: str):
    try:
        deleted = get_services().repository.delete_knowledge_by_title(title)
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted_chunks": deleted, "title": title}


# ---------------------------------------------------------------------------
# Human escalation
# ---------------------------------------------------------------------------
@router.get("/escalations", response_model=list[EscalationOut], tags=["escalations"])
def list_escalations(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return get_services().repository.list_escalations(
            status=status_filter, limit=limit
        )
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc


@router.post("/escalations/{escalation_id}/verdict", tags=["escalations"])
def submit_verdict(escalation_id: str, payload: VerdictRequest):
    """Human-in-the-loop: resolve / reject / reassign an escalated ticket."""
    services = get_services()
    try:
        return services.coordinator.escalation.process_human_verdict(
            escalation_id=escalation_id,
            verdict=payload.verdict,
            resolution=payload.resolution,
            operator=payload.operator or AGENT_HUMAN,
            action=payload.action,
        )
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Verdict failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Dashboard / health
# ---------------------------------------------------------------------------
@router.get("/dashboard/stats", response_model=DashboardStats, tags=["dashboard"])
def dashboard_stats():
    try:
        return get_services().repository.dashboard_stats()
    except DatabaseNotConfiguredError as exc:
        raise _db_error(exc) from exc


@router.get("/health", response_model=HealthOut, tags=["health"])
def health():
    config = validate_configuration()
    database_ok, message = check_database_connection()
    services = get_services()
    return {
        "status": "ok" if database_ok else "degraded",
        "database_ok": database_ok,
        "database_message": message,
        "groq_configured": config["groq_configured"],
        "groq_model": config["groq_model"],
        "embedding_model": config["embedding_model"],
        "app_env": config["app_env"],
        "agents": len(services.coordinator.get_agent_roster()),
    }
