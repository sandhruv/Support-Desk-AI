"""AGENT 3 - Technical Specialist.

Troubleshoots application errors and crashes using REAL RAG:
Supabase pgvector retrieval -> grounded generation -> citation validation.
"""

from __future__ import annotations

import json

from agents.base_agent import AgentResult, BaseAgent, personalize_reply
from llm.groq_client import GroqNotConfiguredError, GroqServiceError
from llm.model_config import AGENT_TECHNICAL
from tools.technical_tools import TechnicalTools


class TechnicalAgent(BaseAgent):
    name = AGENT_TECHNICAL
    plugin_name = "technical_tools"
    description = "Resolves application errors using RAG over the Supabase knowledge base."
    responsibilities = [
        "Resolve application errors and crashes",
        "Troubleshoot login-related technical issues",
        "Search technical FAQs in the knowledge base",
        "Retrieve relevant documents with pgvector",
        "Generate grounded answers and cite sources",
    ]

    def build_plugin(self):
        return TechnicalTools(self.retriever)

    async def _execute(self, ticket: dict, state=None) -> AgentResult:
        message = ticket.get("message", "")
        subject = ticket.get("subject", "")
        ticket_id = ticket.get("id")
        history = (
            self.memory.get_context(ticket_id) if self.memory is not None else ""
        )
        query = f"{subject} {message}".strip()

        # Tool 1: pgvector similarity search (real RAG retrieval)
        search = await self.invoke_tool("search_knowledge_base", query=query, top_k=4)
        results = search.get("results", [])

        if not results or not search.get("is_sufficient"):
            reason = (
                "No sufficiently relevant knowledge base documents were found; "
                "a human specialist should investigate."
            )
            self.repository.update_ticket(
                ticket_id, status="escalated", resolution=reason
            )
            return AgentResult(
                agent_name=self.name,
                success=False,
                output={"search_results": results, "reason": reason},
                sources=[],
                needs_escalation=True,
                escalation_reason=reason,
                reasoning="RAG retrieval returned insufficient context.",
            )

        evidence = self.retriever.format_context(results) if self.retriever else json.dumps(results)[:2000]

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
                    category="technical",
                    history=history,
                )
                reasoning = self.groq.generate_agent_reasoning(
                    self.name,
                    f"Customer technical issue: {message}\n"
                    f"Retrieved sources: {', '.join(search.get('sources', []))}",
                )
            except (GroqServiceError, GroqNotConfiguredError) as exc:
                error = str(exc)
        else:
            error = "GROQ_API_KEY is not configured."

        if not reply:
            reason = "Technical Specialist could not generate a grounded answer."
            return AgentResult(
                agent_name=self.name,
                success=False,
                output={"search_results": results, "llm_error": error},
                sources=search.get("sources", []),
                needs_escalation=True,
                escalation_reason=reason,
                error=error,
                reasoning=reasoning,
            )

        # Replace any customer-name placeholders the model may leave behind.
        reply = personalize_reply(reply, self.repository, ticket)

        # Guarantee an auditable citation footer from the retrieved sources.
        cited_titles = [
            item.get("title")
            for item in results
            if isinstance(item, dict)
            and item.get("title")
            and float(item.get("similarity") or 0.0) >= 0.30
        ]
        source_titles = cited_titles or [
            title for title in search.get("sources", []) if title
        ]
        if source_titles and "[source:" not in reply.lower():
            footer = ", ".join(f"[Source: {title}]" for title in source_titles)
            reply = f"{reply.rstrip()}\n\nSources: {footer}"

        # Tool 2: validate grounding + citations
        validation = await self.invoke_tool(
            "validate_technical_solution",
            solution=reply,
            sources=json.dumps(results, default=str),
        )

        needs_escalation = not validation.get("valid", False)
        escalation_reason = (
            "Generated troubleshooting answer failed grounding/citation validation."
            if needs_escalation
            else ""
        )

        output = {
            "search_results": results,
            "sources": search.get("sources", []),
            "validation": validation,
            "reasoning": reasoning,
            "reply": reply,
            "llm_error": error,
        }

        return AgentResult(
            agent_name=self.name,
            success=True,
            output=output,
            reply=reply,
            sources=search.get("sources", []),
            needs_escalation=needs_escalation,
            escalation_reason=escalation_reason,
            error=error,
            reasoning=reasoning,
        )
