"""Shared ticket state used during one orchestration run.

The state object is created from the database ticket record and passed to
each agent in turn. Every step appends to the execution trace, which is
returned to the API/dashboard and stored in agent logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SharedTicketState:
    ticket_id: str
    user_id: str
    subject: str
    message: str
    category: Optional[str] = None
    confidence: float = 0.0
    assigned_agent: Optional[str] = None
    status: str = "open"
    priority: str = "medium"
    resolution: Optional[str] = None
    conversation_history: str = ""
    classification: dict = field(default_factory=dict)
    specialist_result: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    escalation: dict = field(default_factory=dict)
    escalation_reason: str = ""
    errors: list = field(default_factory=list)
    trace: list = field(default_factory=list)

    # ------------------------------------------------------------------
    @classmethod
    def from_ticket(cls, ticket: dict, history: str = "") -> "SharedTicketState":
        return cls(
            ticket_id=str(ticket.get("id")),
            user_id=str(ticket.get("user_id")),
            subject=ticket.get("subject", ""),
            message=ticket.get("message", ""),
            category=ticket.get("category"),
            confidence=float(ticket.get("confidence") or 0.0),
            assigned_agent=ticket.get("assigned_agent"),
            status=ticket.get("status", "open"),
            priority=ticket.get("priority", "medium"),
            resolution=ticket.get("resolution"),
            conversation_history=history,
            escalation_reason=ticket.get("escalation_reason", "") or "",
        )

    def add_trace(self, agent: str, action: str, detail: str = "", status: str = "ok") -> None:
        self.trace.append(
            {"agent": agent, "action": action, "detail": detail, "status": status}
        )

    def add_error(self, agent: str, error: str) -> None:
        self.errors.append({"agent": agent, "error": error})
        self.add_trace(agent, "error", error, status="error")

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "category": self.category,
            "confidence": self.confidence,
            "assigned_agent": self.assigned_agent,
            "status": self.status,
            "resolution": self.resolution,
            "classification": self.classification,
            "specialist_result": self.specialist_result,
            "sources": self.sources,
            "escalation": self.escalation,
            "errors": self.errors,
            "trace": self.trace,
        }
