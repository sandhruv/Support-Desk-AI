"""Repository layer - every SQL statement lives here.

All persistent state (tickets, conversations, agent logs, knowledge chunks,
escalations, mock payments) is stored in ONE Supabase PostgreSQL database.
Queries are parameterised with SQLAlchemy ``text()`` binds to prevent injection.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text

from database.connection import db_session


def _jsonb(value: Any) -> Optional[str]:
    """Serialise a Python value for a JSONB column."""
    if value is None:
        return None
    if isinstance(value, str):
        value = {"value": value}
    return json.dumps(value, default=str)


def _vector_literal(embedding: list[float]) -> str:
    """pgvector accepts a string literal like '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{float(x):.6f}" for x in embedding) + "]"


def _row(row: Any) -> dict:
    """Convert a SQLAlchemy row mapping into a JSON-friendly dict."""
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, uuid.UUID):
            data[key] = str(value)
        elif isinstance(value, datetime):
            data[key] = value.isoformat()
        elif isinstance(value, Decimal):
            data[key] = float(value)
    return data


class Repository:
    """Data access object for the whole application."""

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def create_user(self, name: str, email: str) -> dict:
        with db_session() as conn:
            conn.execute(
                text(
                    """
                    insert into users (name, email) values (:name, :email)
                    on conflict (email) do nothing
                    """
                ),
                {"name": name, "email": email.strip().lower()},
            )
            row = conn.execute(
                text("select * from users where email = :email"),
                {"email": email.strip().lower()},
            ).mappings().first()
        return _row(row)

    def get_or_create_user(self, name: str, email: str) -> dict:
        existing = self.get_user_by_email(email)
        if existing:
            return existing
        return self.create_user(name, email)

    def get_user(self, user_id: str) -> Optional[dict]:
        with db_session() as conn:
            row = conn.execute(
                text("select * from users where id = :id"), {"id": user_id}
            ).mappings().first()
        return _row(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[dict]:
        with db_session() as conn:
            row = conn.execute(
                text("select * from users where email = :email"),
                {"email": (email or "").strip().lower()},
            ).mappings().first()
        return _row(row) if row else None

    # ------------------------------------------------------------------
    # Tickets
    # ------------------------------------------------------------------
    def create_ticket(
        self,
        user_id: str,
        subject: str,
        message: str,
        priority: str = "medium",
    ) -> dict:
        with db_session() as conn:
            row = conn.execute(
                text(
                    """
                    insert into tickets (user_id, subject, message, priority)
                    values (:user_id, :subject, :message, :priority)
                    returning *
                    """
                ),
                {
                    "user_id": user_id,
                    "subject": subject,
                    "message": message,
                    "priority": priority,
                },
            ).mappings().first()
        return _row(row)

    def get_ticket(self, ticket_id: str) -> Optional[dict]:
        with db_session() as conn:
            row = conn.execute(
                text("select * from tickets where id = :id"), {"id": ticket_id}
            ).mappings().first()
        return _row(row) if row else None

    def list_tickets(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict]:
        clauses, params = [], {"limit": int(limit)}
        if category:
            clauses.append("category = :category")
            params["category"] = category
        if status:
            clauses.append("status = :status")
            params["status"] = status
        if priority:
            clauses.append("priority = :priority")
            params["priority"] = priority
        if search:
            clauses.append("(subject ilike :search or message ilike :search)")
            params["search"] = f"%{search}%"
        where = f"where {' and '.join(clauses)}" if clauses else ""
        with db_session() as conn:
            rows = conn.execute(
                text(
                    f"select * from tickets {where} order by created_at desc limit :limit"
                ),
                params,
            ).mappings().all()
        return [_row(r) for r in rows]

    _TICKET_FIELDS = {
        "category",
        "confidence",
        "status",
        "assigned_agent",
        "resolution",
        "priority",
        "subject",
        "message",
    }

    def update_ticket(self, ticket_id: str, **fields) -> Optional[dict]:
        """Update whitelisted ticket fields (safe dynamic SET clause)."""
        allowed = {k: v for k, v in fields.items() if k in self._TICKET_FIELDS}
        if not allowed:
            return self.get_ticket(ticket_id)
        assignments = ", ".join(f"{column} = :{column}" for column in allowed)
        params = {"ticket_id": ticket_id, **allowed}
        with db_session() as conn:
            row = conn.execute(
                text(
                    f"update tickets set {assignments}, updated_at = now() "
                    "where id = :ticket_id returning *"
                ),
                params,
            ).mappings().first()
        return _row(row) if row else None

    # ------------------------------------------------------------------
    # Conversations (persistent shared memory)
    # ------------------------------------------------------------------
    def add_conversation(
        self, ticket_id: str, user_id: Optional[str], role: str, message: str
    ) -> dict:
        with db_session() as conn:
            row = conn.execute(
                text(
                    """
                    insert into conversations (ticket_id, user_id, role, message)
                    values (:ticket_id, :user_id, :role, :message)
                    returning *
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "user_id": user_id,
                    "role": role,
                    "message": message,
                },
            ).mappings().first()
        return _row(row)

    def get_conversation(self, ticket_id: str) -> list[dict]:
        with db_session() as conn:
            rows = conn.execute(
                text(
                    "select * from conversations where ticket_id = :id "
                    "order by created_at asc"
                ),
                {"id": ticket_id},
            ).mappings().all()
        return [_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Agent logs (append-only audit trail)
    # ------------------------------------------------------------------
    def log_agent(
        self,
        ticket_id: Optional[str],
        agent_name: str,
        action: str,
        input_data: Any = None,
        output_data: Any = None,
        status: str = "success",
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> str:
        with db_session() as conn:
            row = conn.execute(
                text(
                    """
                    insert into agent_logs
                        (ticket_id, agent_name, action, input_data, output_data,
                         execution_status, error_message, duration_ms)
                    values
                        (:ticket_id, :agent_name, :action,
                         cast(:input_data as jsonb), cast(:output_data as jsonb),
                         :status, :error, :duration_ms)
                    returning id
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "agent_name": agent_name,
                    "action": action,
                    "input_data": _jsonb(input_data) or "{}",
                    "output_data": _jsonb(output_data) or "{}",
                    "status": status,
                    "error": error,
                    "duration_ms": duration_ms,
                },
            ).mappings().first()
        return str(row["id"])

    def list_agent_logs(
        self,
        ticket_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict]:
        clauses, params = [], {"limit": int(limit)}
        if ticket_id:
            clauses.append("ticket_id = :ticket_id")
            params["ticket_id"] = ticket_id
        if agent_name:
            clauses.append("agent_name = :agent_name")
            params["agent_name"] = agent_name
        where = f"where {' and '.join(clauses)}" if clauses else ""
        with db_session() as conn:
            rows = conn.execute(
                text(
                    f"select * from agent_logs {where} "
                    "order by created_at desc limit :limit"
                ),
                params,
            ).mappings().all()
        return [_row(r) for r in rows]

    def agent_performance(self) -> list[dict]:
        with db_session() as conn:
            rows = conn.execute(
                text(
                    """
                    select agent_name,
                           count(*) as runs,
                           count(*) filter (where execution_status = 'error') as errors,
                           round(avg(duration_ms)) as avg_duration_ms,
                           max(created_at) as last_activity
                    from agent_logs
                    group by agent_name
                    order by runs desc
                    """
                )
            ).mappings().all()
        return [_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Knowledge base (pgvector)
    # ------------------------------------------------------------------
    def insert_knowledge_document(
        self,
        title: str,
        content: str,
        category: Optional[str],
        embedding: Optional[list[float]],
        metadata: Optional[dict] = None,
    ) -> str:
        with db_session() as conn:
            row = conn.execute(
                text(
                    """
                    insert into knowledge_documents
                        (title, content, category, embedding, metadata)
                    values
                        (:title, :content, :category,
                         cast(:embedding as vector), cast(:metadata as jsonb))
                    returning id
                    """
                ),
                {
                    "title": title,
                    "content": content,
                    "category": category,
                    "embedding": _vector_literal(embedding) if embedding else None,
                    "metadata": _jsonb(metadata or {}),
                },
            ).mappings().first()
        return str(row["id"])

    def delete_knowledge_by_title(self, title: str) -> int:
        with db_session() as conn:
            result = conn.execute(
                text("delete from knowledge_documents where title = :title"),
                {"title": title},
            )
            return result.rowcount or 0

    def list_knowledge(self) -> list[dict]:
        """One summary row per document title."""
        with db_session() as conn:
            rows = conn.execute(
                text(
                    """
                    select title, category,
                           count(*) as chunks,
                           min(created_at) as created_at,
                           (array_agg(content order by (metadata->>'chunk_index')::int))[1]
                               as preview,
                           bool_and(embedding is not null) as embedded
                    from knowledge_documents
                    group by title, category
                    order by title
                    """
                )
            ).mappings().all()
        result = []
        for r in rows:
            d = _row(r)
            d["preview"] = (d.get("preview") or "")[:240]
            result.append(d)
        return result

    def similarity_search(
        self,
        embedding: list[float],
        top_k: int = 4,
        category: Optional[str] = None,
        threshold: float = 0.0,
    ) -> list[dict]:
        with db_session() as conn:
            rows = conn.execute(
                text(
                    """
                    select * from match_knowledge_chunks(
                        cast(:embedding as vector),
                        :threshold, :match_count, :category
                    )
                    """
                ),
                {
                    "embedding": _vector_literal(embedding),
                    "threshold": float(threshold),
                    "match_count": int(top_k),
                    "category": category,
                },
            ).mappings().all()
        return [_row(r) for r in rows]

    def knowledge_stats(self) -> dict:
        with db_session() as conn:
            row = conn.execute(
                text(
                    "select count(*) as chunks, count(distinct title) as documents "
                    "from knowledge_documents"
                )
            ).mappings().first()
        return _row(row)

    # ------------------------------------------------------------------
    # Mock payment records (billing agent only - no real transactions)
    # ------------------------------------------------------------------
    def lookup_payment_records(
        self, user_id: Optional[str] = None, transaction_ref: Optional[str] = None
    ) -> list[dict]:
        clauses, params = [], {}
        if user_id:
            clauses.append("user_id = :user_id")
            params["user_id"] = user_id
        if transaction_ref:
            clauses.append("upper(transaction_ref) = upper(:ref)")
            params["ref"] = transaction_ref
        where = f"where {' and '.join(clauses)}" if clauses else ""
        with db_session() as conn:
            rows = conn.execute(
                text(
                    f"select * from payment_records {where} "
                    "order by created_at desc limit 20"
                ),
                params,
            ).mappings().all()
        return [_row(r) for r in rows]

    def insert_payment_record(
        self,
        user_id: str,
        transaction_ref: str,
        amount: float,
        status: str,
        description: str,
        currency: str = "USD",
    ) -> dict:
        with db_session() as conn:
            row = conn.execute(
                text(
                    """
                    insert into payment_records
                        (user_id, transaction_ref, amount, status, description, currency)
                    values
                        (:user_id, :ref, :amount, :status, :description, :currency)
                    on conflict (transaction_ref) do nothing
                    returning *
                    """
                ),
                {
                    "user_id": user_id,
                    "ref": transaction_ref,
                    "amount": amount,
                    "status": status,
                    "description": description,
                    "currency": currency,
                },
            ).mappings().first()
        if row:
            return _row(row)
        found = self.lookup_payment_records(transaction_ref=transaction_ref)
        return found[0] if found else {}

    # ------------------------------------------------------------------
    # Escalations
    # ------------------------------------------------------------------
    def create_escalation(
        self,
        ticket_id: str,
        reason: str,
        priority: str = "high",
        assigned_to: str = "Human Support Queue",
    ) -> dict:
        with db_session() as conn:
            row = conn.execute(
                text(
                    """
                    insert into escalations (ticket_id, reason, priority, assigned_to)
                    values (:ticket_id, :reason, :priority, :assigned_to)
                    returning *
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "reason": reason,
                    "priority": priority,
                    "assigned_to": assigned_to,
                },
            ).mappings().first()
        return _row(row)

    def get_escalation(self, escalation_id: str) -> Optional[dict]:
        with db_session() as conn:
            row = conn.execute(
                text("select * from escalations where id = :id"),
                {"id": escalation_id},
            ).mappings().first()
        return _row(row) if row else None

    def get_escalation_by_ticket(self, ticket_id: str) -> Optional[dict]:
        with db_session() as conn:
            row = conn.execute(
                text(
                    "select * from escalations where ticket_id = :ticket_id "
                    "order by created_at desc limit 1"
                ),
                {"ticket_id": ticket_id},
            ).mappings().first()
        return _row(row) if row else None

    def list_escalations(self, status: Optional[str] = None, limit: int = 100) -> list[dict]:
        params = {"limit": int(limit)}
        where = ""
        if status:
            where = "where e.status = :status"
            params["status"] = status
        with db_session() as conn:
            rows = conn.execute(
                text(
                    f"""
                    select e.*, t.subject, t.message, t.category, t.confidence,
                           t.status as ticket_status, u.name as customer_name,
                           u.email as customer_email
                    from escalations e
                    join tickets t on t.id = e.ticket_id
                    join users u on u.id = t.user_id
                    {where}
                    order by
                        case e.priority
                            when 'urgent' then 0 when 'high' then 1
                            when 'medium' then 2 else 3 end,
                        e.created_at desc
                    limit :limit
                    """
                ),
                params,
            ).mappings().all()
        return [_row(r) for r in rows]

    _ESCALATION_FIELDS = {"status", "human_verdict", "assigned_to", "priority", "reason"}

    def update_escalation(self, escalation_id: str, **fields) -> Optional[dict]:
        allowed = {k: v for k, v in fields.items() if k in self._ESCALATION_FIELDS}
        resolved = allowed.get("status") in ("resolved", "rejected")
        if not allowed and not resolved:
            return self.get_escalation(escalation_id)
        assignments = ", ".join(f"{c} = :{c}" for c in allowed)
        if resolved:
            assignments = (assignments + ", " if assignments else "") + "resolved_at = now()"
        params = {"escalation_id": escalation_id, **allowed}
        with db_session() as conn:
            row = conn.execute(
                text(
                    f"update escalations set {assignments} "
                    "where id = :escalation_id returning *"
                ),
                params,
            ).mappings().first()
        return _row(row) if row else None

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    def dashboard_stats(self) -> dict:
        with db_session() as conn:
            totals = conn.execute(
                text(
                    """
                    select
                        count(*) as total,
                        count(*) filter (where status = 'resolved') as resolved,
                        count(*) filter (where status in ('open', 'processing', 'pending')) as pending,
                        count(*) filter (where status = 'escalated') as escalated,
                        count(*) filter (where status = 'failed') as failed
                    from tickets
                    """
                )
            ).mappings().first()
            categories = conn.execute(
                text(
                    """
                    select coalesce(category, 'unclassified') as category, count(*) as count
                    from tickets group by 1 order by count desc
                    """
                )
            ).mappings().all()
            statuses = conn.execute(
                text("select status, count(*) as count from tickets group by 1")
            ).mappings().all()
            recent = conn.execute(
                text(
                    """
                    select id, subject, category, status, priority, assigned_agent, created_at
                    from tickets order by created_at desc limit 10
                    """
                )
            ).mappings().all()
            escalations = conn.execute(
                text(
                    "select count(*) as total, "
                    "count(*) filter (where status = 'pending') as pending "
                    "from escalations"
                )
            ).mappings().first()

        total = int(totals["total"] or 0)
        resolved = int(totals["resolved"] or 0)
        stats = _row(totals)
        stats["resolution_rate"] = round(resolved / total, 3) if total else 0.0
        stats["category_distribution"] = [_row(r) for r in categories]
        stats["status_distribution"] = [_row(r) for r in statuses]
        stats["recent_tickets"] = [_row(r) for r in recent]
        stats["agent_performance"] = self.agent_performance()
        stats["escalations"] = _row(escalations)
        return stats

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def ping(self) -> bool:
        with db_session() as conn:
            conn.execute(text("select 1"))
        return True
