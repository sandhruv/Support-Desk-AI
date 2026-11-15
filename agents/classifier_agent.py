"""AGENT 1 - Classifier Agent.

Reads the incoming complaint, identifies intent, extracts the issue,
produces a confidence score and assigns the correct specialist.
LLM classification is validated by deterministic Python tools.
"""

from __future__ import annotations

from agents.base_agent import AgentResult, BaseAgent
from llm.groq_client import GroqNotConfiguredError, GroqServiceError
from llm.model_config import (
    AGENT_CLASSIFIER,
    AGENT_ESCALATION,
    CONFIDENCE_THRESHOLD,
)
from tools.classification_tools import (
    ClassificationTools,
    classification_validation_tool,
    keyword_classification_tool,
)


class ClassifierAgent(BaseAgent):
    name = AGENT_CLASSIFIER
    plugin_name = "classification_tools"
    description = "Classifies customer complaints and routes them to the right specialist."
    responsibilities = [
        "Read incoming customer complaints",
        "Identify the ticket category (billing/technical/account/other)",
        "Extract the core issue",
        "Produce a confidence score",
        "Assign the correct specialist agent",
    ]

    def build_plugin(self):
        return ClassificationTools()

    async def _execute(self, ticket: dict, state=None) -> AgentResult:
        message = ticket.get("message", "")
        subject = ticket.get("subject", "")

        # Tool 1: deterministic keyword scoring
        keyword = await self.invoke_tool(
            "keyword_classification_tool", message=message, subject=subject
        )

        llm_result = None
        llm_error = None
        if self.groq.available:
            try:
                llm_result = self.groq.classify_ticket(message=message, subject=subject)
            except (GroqServiceError, GroqNotConfiguredError) as exc:
                llm_error = str(exc)
        else:
            llm_error = "GROQ_API_KEY is not configured; keyword fallback used."

        # Tool 2: validation / normalisation
        if llm_result:
            validation = await self.invoke_tool(
                "classification_validation_tool",
                category=llm_result["category"],
                confidence=llm_result["confidence"],
                message=message,
            )
            issue = llm_result.get("issue") or "Customer support request"
            reasoning = llm_result.get("reasoning") or ""
        else:
            validation = await self.invoke_tool(
                "classification_validation_tool",
                category=keyword.get("category", "other"),
                confidence=keyword.get("confidence", 0.0),
                message=message,
            )
            issue = f"Keyword classification: {keyword.get('category', 'other')} request"
            reasoning = keyword.get("notes", "Deterministic keyword fallback.")

        category = validation.get("category", "other")
        confidence = float(validation.get("confidence", 0.0))
        from orchestration.routing import CATEGORY_TO_AGENT

        assigned_agent = CATEGORY_TO_AGENT.get(category, AGENT_ESCALATION)
        needs_escalation = bool(validation.get("needs_escalation")) or (
            confidence < CONFIDENCE_THRESHOLD
        )

        self.repository.update_ticket(
            ticket["id"],
            category=category,
            confidence=confidence,
            assigned_agent=assigned_agent,
        )

        output = {
            "category": category,
            "confidence": confidence,
            "issue": issue,
            "assigned_agent": assigned_agent,
            "reasoning": reasoning,
            "validation_notes": validation.get("notes", []),
            "llm_used": llm_result is not None,
            "llm_error": llm_error,
            "keyword_scores": keyword.get("scores", {}),
            "needs_escalation": needs_escalation,
        }

        return AgentResult(
            agent_name=self.name,
            success=True,
            output=output,
            reply="",
            used_tools=["keyword_classification_tool", "classification_validation_tool"],
            needs_escalation=needs_escalation,
            escalation_reason=(
                f"Low classification confidence ({confidence:.0%})."
                if needs_escalation
                else ""
            ),
            reasoning=reasoning,
        )
