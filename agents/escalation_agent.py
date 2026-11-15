"""AGENT 5 - Escalation Router.

Creates human escalation records, assigns tickets to the human queue and
applies human verdicts (resolve / reject / reassign).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agents.base_agent import AgentResult, BaseAgent
from llm.groq_client import GroqNotConfiguredError, GroqServiceError
from llm.model_config import AGENT_ESCALATION, AGENT_HUMAN, CONFIDENCE_THRESHOLD
from tools.escalation_tools import EscalationTools


class EscalationAgent(BaseAgent):
    name = AGENT_ESCALATION
    plugin_name = "escalation_tools"
    description = "Routes unresolved or low-confidence tickets to human support."
    responsibilities = [
        "Identify unresolved and low-confidence complaints",
        "Create human escalation records",
        "Assign tickets to the human support queue",
        "Record escalation reasons and priorities",
        "Process human verdicts and update ticket status",
    ]

    def build_plugin(self):
        return EscalationTools(self.repository)

    async def _execute(self, ticket: dict, state=None) -> AgentResult:
        ticket_id = ticket.get("id")
        message = ticket.get("message", "")
        subject = ticket.get("subject", "")
        confidence = float(ticket.get("confidence") or 0.0)

        reason = ""
        if state is not None and getattr(state, "escalation_reason", ""):
            reason = state.escalation_reason
        if not reason:
            if confidence < CONFIDENCE_THRESHOLD:
                reason = (
                    f"Classification confidence is {confidence:.0%}, below the "
                    f"{CONFIDENCE_THRESHOLD:.0%} automated-resolution threshold."
                )
            elif not ticket.get("category") or ticket.get("category") == "other":
                reason = "Ticket could not be confidently classified into a supported category."
            else:
                reason = (
                    "The automated specialist could not resolve the ticket with "
                    "sufficient evidence; human review is required."
                )

        llm_reason = ""
        if self.groq.available:
            try:
                llm_reason = self.groq.generate_response(
                    "You are the Escalation Router. In 2 sentences explain why this "
                    "ticket needs human support. Mention the risk and what to check.",
                    f"Subject: {subject}\nMessage: {message}\nReason: {reason}",
                    temperature=0.2,
                    max_tokens=180,
                )
            except (GroqServiceError, GroqNotConfiguredError):
                llm_reason = ""

        full_reason = reason
        if llm_reason:
            full_reason = f"{reason} Summary: {llm_reason}".strip()

        priority = "urgent" if ticket.get("priority") in ("urgent", "high") else "high"

        # Tool 1: create the escalation record
        escalation = await self.invoke_tool(
            "create_escalation_ticket",
            ticket_id=ticket_id,
            reason=full_reason[:1500],
            priority=priority,
        )
        # Tool 2: verify queue status
        status = await self.invoke_tool(
            "check_escalation_status", ticket_id=ticket_id
        )

        output = {
            "escalation": escalation,
            "status": status,
            "reason": full_reason,
            "human_summary": llm_reason,
            "priority": priority,
        }

        return AgentResult(
            agent_name=self.name,
            success=bool(escalation),
            output=output,
            reply=(
                "Your case has been escalated to our human support team for "
                "review. You will receive an update once a specialist has "
                "reviewed your ticket."
            ),
            needs_escalation=True,
            escalation_reason=full_reason,
            reasoning=llm_reason or reason,
        )

    # ------------------------------------------------------------------
    # Human-in-the-loop verdict processing
    # ------------------------------------------------------------------
    def process_human_verdict(
        self,
        escalation_id: str,
        verdict: str,
        resolution: str = "",
        operator: str = AGENT_HUMAN,
        action: str = "resolve",
    ) -> dict:
        """Apply a human decision to an escalation and its ticket.

        action: 'resolve' | 'reject' | 'reassign'
        """
        if action not in ("resolve", "reject", "reassign"):
            raise ValueError("action must be resolve, reject or reassign")
        escalation = self.repository.get_escalation(escalation_id)
        if not escalation:
            raise ValueError(f"Escalation not found: {escalation_id}")

        ticket_id = escalation["ticket_id"]
        status_map = {"resolve": "resolved", "reject": "rejected", "reassign": "reassigned"}
        ticket_status_map = {"resolve": "resolved", "reject": "open", "reassign": "processing"}

        updated = self.repository.update_escalation(
            escalation_id,
            status=status_map[action],
            human_verdict=verdict,
        )
        ticket = self.repository.update_ticket(
            ticket_id,
            status=ticket_status_map[action],
            resolution=resolution or verdict,
            assigned_agent=operator,
        )

        if self.memory is not None and (resolution or verdict):
            self.memory.add_human_message(
                ticket_id,
                resolution or verdict,
                user_id=escalation.get("user_id") if isinstance(escalation, dict) else None,
            )

        self._log(
            ticket_id=ticket_id,
            action="human_verdict",
            input_data={
                "escalation_id": escalation_id,
                "verdict": verdict,
                "action": action,
                "operator": operator,
            },
            output_data={"escalation": updated, "ticket_status": ticket_status_map[action]},
            status="success",
        )
        # Separate audit entry attributed to the human operator
        try:
            self.repository.log_agent(
                ticket_id=ticket_id,
                agent_name=AGENT_HUMAN,
                action="human_verdict",
                input_data={
                    "escalation_id": escalation_id,
                    "verdict": verdict,
                    "action": action,
                },
                output_data={
                    "resolution": resolution or verdict,
                    "ticket_status": ticket_status_map[action],
                },
                status="success",
            )
        except Exception:
            pass

        return {
            "escalation": updated,
            "ticket": ticket,
            "action": action,
            "ticket_status": ticket_status_map[action],
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
