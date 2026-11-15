"""Escalation Router tools.

Two real Python tools:
1. create_escalation_ticket()  -> inserts into Supabase + updates ticket
2. check_escalation_status()   -> reads the escalation queue state
"""

from __future__ import annotations

import json

from semantic_kernel.functions import kernel_function


def create_escalation_ticket(
    repository,
    ticket_id: str,
    reason: str,
    priority: str = "high",
    assigned_to: str = "Human Support Queue",
) -> dict:
    """Create a human escalation record and mark the ticket escalated."""
    priority = priority if priority in ("low", "medium", "high", "urgent") else "high"
    escalation = repository.create_escalation(
        ticket_id=ticket_id,
        reason=reason,
        priority=priority,
        assigned_to=assigned_to,
    )
    repository.update_ticket(
        ticket_id,
        status="escalated",
        assigned_agent=assigned_to,
        resolution=reason,
    )
    return escalation


def check_escalation_status(repository, ticket_id: str) -> dict:
    """Return the latest escalation for a ticket (or a not-found marker)."""
    escalation = repository.get_escalation_by_ticket(ticket_id)
    return {
        "found": escalation is not None,
        "escalation": escalation,
    }


class EscalationTools:
    """Semantic Kernel plugin exposing the escalation tools."""

    plugin_name = "escalation_tools"

    def __init__(self, repository):
        self.repository = repository

    @kernel_function(name="create_escalation_ticket", description="Create a human escalation ticket.")
    def create_tool(self, ticket_id: str, reason: str, priority: str = "high") -> str:
        return json.dumps(
            create_escalation_ticket(self.repository, ticket_id, reason, priority)
        )

    @kernel_function(name="check_escalation_status", description="Check the escalation status for a ticket.")
    def status_tool(self, ticket_id: str) -> str:
        return json.dumps(check_escalation_status(self.repository, ticket_id))

    @property
    def direct(self) -> dict:
        return {
            "create_escalation_ticket": lambda **kwargs: create_escalation_ticket(
                self.repository, **kwargs
            ),
            "check_escalation_status": lambda **kwargs: check_escalation_status(
                self.repository, **kwargs
            ),
        }
