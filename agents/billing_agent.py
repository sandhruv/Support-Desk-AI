"""AGENT 2 - Billing Specialist.

Handles payment problems, duplicate charges, refunds and invoices using
mock payment records stored in Supabase plus billing policy tools.

It NEVER claims a refund has been processed - there is no payment gateway
integration, so replies stay within policy wording.
"""

from __future__ import annotations

import json

from agents.base_agent import AgentResult, BaseAgent, personalize_reply
from llm.groq_client import GroqNotConfiguredError, GroqServiceError
from llm.model_config import AGENT_BILLING
from tools.billing_tools import BillingTools, extract_transaction_reference


class BillingAgent(BaseAgent):
    name = AGENT_BILLING
    plugin_name = "billing_tools"
    description = "Resolves payment, duplicate charge, refund and invoice questions."
    responsibilities = [
        "Handle payment problems",
        "Investigate duplicate transaction complaints",
        "Answer refund and invoice questions",
        "Check billing policies",
        "Retrieve mock transaction records from Supabase",
        "Generate customer-friendly responses grounded in records",
    ]

    def build_plugin(self):
        return BillingTools(self.repository)

    async def _execute(self, ticket: dict, state=None) -> AgentResult:
        message = ticket.get("message", "")
        subject = ticket.get("subject", "")
        ticket_id = ticket.get("id")
        history = (
            self.memory.get_context(ticket_id) if self.memory is not None else ""
        )

        # Follow-up support: recover a TXN reference from earlier messages
        transaction_ref = extract_transaction_reference(message)
        if not transaction_ref and self.memory is not None:
            transaction_ref = self.memory.find_transaction_reference(ticket_id)

        # Tool 1: mock payment records from Supabase
        payment = await self.invoke_tool(
            "lookup_payment_record",
            user_id=ticket.get("user_id", ""),
            transaction_ref=transaction_ref or "",
        )
        # Tool 2: billing policy
        policy = await self.invoke_tool("check_billing_policy", topic=message)

        needs_escalation = False
        escalation_reason = ""
        if transaction_ref and not payment.get("found"):
            needs_escalation = True
            escalation_reason = (
                f"No payment record found for reference {transaction_ref}; "
                "a human should verify the transaction."
            )

        evidence = (
            f"Payment lookup (transaction_ref={transaction_ref or 'not provided'}):\n"
            f"{json.dumps(payment, default=str)[:1800]}\n\n"
            f"Policy ({policy.get('topic')}):\n{policy.get('policy', '')}"
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
                    category="billing",
                    history=history,
                )
                reasoning = self.groq.generate_agent_reasoning(
                    self.name,
                    f"Customer billing issue: {message}\n"
                    f"Tool evidence: {evidence[:1200]}",
                )
            except (GroqServiceError, GroqNotConfiguredError) as exc:
                error = str(exc)
                needs_escalation = True
                escalation_reason = escalation_reason or (
                    "Billing Specialist could not generate a reply - LLM unavailable."
                )
        else:
            error = "GROQ_API_KEY is not configured."
            needs_escalation = True
            escalation_reason = "Billing Specialist requires the LLM service, which is not configured."

        reply = personalize_reply(reply, self.repository, ticket)

        output = {
            "policy_topic": policy.get("topic"),
            "policy": policy.get("policy"),
            "transaction_ref": transaction_ref,
            "payment_records": payment.get("records", []),
            "payment_found": payment.get("found", False),
            "reasoning": reasoning,
            "reply": reply,
            "llm_error": error,
        }

        return AgentResult(
            agent_name=self.name,
            success=bool(reply),
            output=output,
            reply=reply,
            sources=[],
            needs_escalation=needs_escalation,
            escalation_reason=escalation_reason,
            error=error,
            reasoning=reasoning,
        )
