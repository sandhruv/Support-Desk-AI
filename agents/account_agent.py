"""AGENT 4 - Account Specialist.

Handles login problems, account access and password-reset guidance.
Passwords are never stored, requested or accepted.
"""

from __future__ import annotations

import json

from agents.base_agent import AgentResult, BaseAgent, personalize_reply
from llm.groq_client import GroqNotConfiguredError, GroqServiceError
from llm.model_config import AGENT_ACCOUNT
from tools.account_tools import AccountTools, extract_email


class AccountAgent(BaseAgent):
    name = AGENT_ACCOUNT
    plugin_name = "account_tools"
    description = "Resolves login, password reset and account access issues safely."
    responsibilities = [
        "Handle login and account access problems",
        "Provide password reset and recovery guidance",
        "Check account records in Supabase",
        "Validate requests for password safety",
        "Escalate when identity verification is needed",
    ]

    def build_plugin(self):
        return AccountTools(self.repository)

    async def _execute(self, ticket: dict, state=None) -> AgentResult:
        message = ticket.get("message", "")
        subject = ticket.get("subject", "")
        ticket_id = ticket.get("id")
        history = (
            self.memory.get_context(ticket_id) if self.memory is not None else ""
        )

        # Tool 1: safety validation (never handle plaintext passwords)
        safety = await self.invoke_tool(
            "validate_account_support_request", message=message
        )
        # Tool 2: customer account lookup from Supabase
        email = extract_email(message) or ""
        account = await self.invoke_tool(
            "lookup_customer_account",
            user_id=ticket.get("user_id", ""),
            email=email,
        )

        needs_escalation = False
        escalation_reason = ""
        if not account.get("found"):
            needs_escalation = True
            escalation_reason = (
                "Customer account could not be located; identity verification "
                "by a human is required."
            )
        if not safety.get("safe_to_proceed", True):
            needs_escalation = True
            escalation_reason = (
                escalation_reason
                or "Account request contains unsafe content; human review required."
            )

        safe_user = account.get("user") or {}
        evidence = (
            "Safe recovery guidance:\n"
            f"{safety.get('guidance', '')}\n\n"
            f"Safety validation: {json.dumps(safety, default=str)}\n\n"
            f"Account record found: {account.get('found')}\n"
            f"Registered email: {safe_user.get('email', 'not found')}\n"
            f"Name: {safe_user.get('name', 'not found')}\n"
            f"Recent tickets: {len(account.get('tickets', []))}"
        )

        reply = ""
        reasoning = ""
        error = None
        if self.groq.available:
            try:
                reply = self.groq.generate_customer_reply(
                    agent_name=self.name,
                    subject=subject,
                    message=message,
                    evidence=evidence,
                    category="account",
                    history=history,
                )
                reasoning = self.groq.generate_agent_reasoning(
                    self.name,
                    f"Customer account issue: {message}\n"
                    f"Account found: {account.get('found')}",
                )
            except (GroqServiceError, GroqNotConfiguredError) as exc:
                error = str(exc)
                needs_escalation = True
                escalation_reason = (
                    escalation_reason
                    or "Account Specialist could not generate a reply - LLM unavailable."
                )
        else:
            error = "GROQ_API_KEY is not configured."
            needs_escalation = True
            escalation_reason = "Account Specialist requires the LLM service, which is not configured."

        reply = personalize_reply(reply, self.repository, ticket)

        output = {
            "account_found": account.get("found", False),
            "customer_email": safe_user.get("email"),
            "recent_ticket_count": account.get("ticket_count", 0),
            "safety": safety,
            "reasoning": reasoning,
            "reply": reply,
            "llm_error": error,
        }

        return AgentResult(
            agent_name=self.name,
            success=bool(reply),
            output=output,
            reply=reply,
            needs_escalation=needs_escalation,
            escalation_reason=escalation_reason,
            error=error,
            reasoning=reasoning,
        )
