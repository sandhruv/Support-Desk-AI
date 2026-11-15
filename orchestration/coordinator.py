"""Multi-agent coordinator (router-to-specialists architecture).

Workflow:
    Customer -> Classifier Agent -> routing decision
             -> Billing / Technical / Account Specialist
             -> (on low confidence / unresolved) Escalation Router
             -> Human Support -> Final Resolution

The coordinator owns the shared ticket state, performs real agent handoffs,
saves every conversation message in Supabase and records an execution trace.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from semantic_kernel.functions import KernelArguments

from agents.account_agent import AccountAgent
from agents.billing_agent import BillingAgent
from agents.classifier_agent import ClassifierAgent
from agents.escalation_agent import EscalationAgent
from agents.technical_agent import TechnicalAgent
from llm.groq_client import GroqClient
from llm.model_config import (
    AGENT_ACCOUNT,
    AGENT_BILLING,
    AGENT_CLASSIFIER,
    AGENT_ESCALATION,
    AGENT_TECHNICAL,
    CONFIDENCE_THRESHOLD,
)
from llm.sk_integration import build_semantic_kernel
from memory.conversation_memory import ConversationMemory
from orchestration.routing import RoutingTools, route_ticket
from orchestration.shared_state import SharedTicketState
from rag.retriever import KnowledgeRetriever

logger = logging.getLogger(__name__)


class TicketNotFoundError(ValueError):
    pass


class SupportCoordinator:
    def __init__(
        self,
        repository,
        groq: Optional[GroqClient] = None,
        memory: Optional[ConversationMemory] = None,
        retriever: Optional[KnowledgeRetriever] = None,
        kernel=None,
    ):
        self.repository = repository
        self.groq = groq or GroqClient()
        self.memory = memory or ConversationMemory(repository)
        self.retriever = retriever or KnowledgeRetriever(repository)
        self.kernel = kernel or build_semantic_kernel()

        # Register the routing plugin on the shared kernel
        try:
            self.kernel.add_plugin(RoutingTools(), plugin_name="routing_tools")
        except Exception as exc:  # pragma: no cover - SK version guard
            logger.warning("Could not register routing plugin: %s", exc)

        self.classifier = ClassifierAgent(
            repository, groq=self.groq, memory=self.memory, kernel=self.kernel
        )
        self.billing = BillingAgent(
            repository, groq=self.groq, memory=self.memory, kernel=self.kernel
        )
        self.technical = TechnicalAgent(
            repository,
            groq=self.groq,
            memory=self.memory,
            retriever=self.retriever,
            kernel=self.kernel,
        )
        self.account = AccountAgent(
            repository, groq=self.groq, memory=self.memory, kernel=self.kernel
        )
        self.escalation = EscalationAgent(
            repository, groq=self.groq, memory=self.memory, kernel=self.kernel
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def process_ticket(self, ticket_id: str) -> dict:
        """Run the complete multi-agent pipeline for one ticket."""
        started = time.perf_counter()
        ticket = self.repository.get_ticket(ticket_id)
        if not ticket:
            raise TicketNotFoundError(f"Ticket not found: {ticket_id}")

        self.repository.update_ticket(ticket_id, status="processing")
        history = self.memory.get_context(ticket_id)
        state = SharedTicketState.from_ticket(ticket, history)
        state.add_trace("Support Coordinator", "start", f"Ticket {ticket_id} received")
        self._log(ticket_id, "process_start", {"ticket_id": ticket_id})

        try:
            # ---------------- 1. Classification ----------------
            classification = await self.classifier.run(ticket, state)
            state.add_trace(
                AGENT_CLASSIFIER,
                "classify",
                f"category={classification.output.get('category')} "
                f"confidence={classification.output.get('confidence')}",
            )
            state.classification = classification.to_dict()

            if not classification.success:
                state.add_error(AGENT_CLASSIFIER, classification.error or "classification failed")

            category = classification.output.get("category", "other")
            confidence = float(classification.output.get("confidence", 0.0) or 0.0)
            state.category = category
            state.confidence = confidence
            self.repository.update_ticket(
                ticket_id,
                category=category,
                confidence=confidence,
                assigned_agent=classification.output.get("assigned_agent"),
            )

            # ---------------- 2. Routing ----------------
            route = await self._route(category, confidence)
            state.add_trace(
                "Support Coordinator",
                "route",
                route.get("reason", ""),
            )

            if route.get("escalate"):
                final = await self._escalate(
                    ticket, state, reason=classification.escalation_reason or route.get("reason", "")
                )
                return self._finish(ticket_id, state, final, started, status="escalated")

            # ---------------- 3. Specialist handoff ------------
            specialist = self._agent_for(route.get("next_agent"))
            if specialist is None:
                final = await self._escalate(
                    ticket, state, reason="No specialist available for this category."
                )
                return self._finish(ticket_id, state, final, started, status="escalated")

            state.add_trace(
                "Support Coordinator",
                "handoff",
                f"{AGENT_CLASSIFIER} -> {specialist.name}",
            )
            result = await specialist.run(ticket, state)
            state.specialist_result = result.to_dict()
            state.sources = result.sources
            state.assigned_agent = specialist.name
            state.add_trace(
                specialist.name,
                "specialist_run",
                f"success={result.success} escalate={result.needs_escalation}",
                status="ok" if result.success else "error",
            )

            # ---------------- 4. Escalation fallback -----------
            if result.needs_escalation or not result.success:
                reason = result.escalation_reason or (
                    f"{specialist.name} could not resolve the ticket."
                )
                final = await self._escalate(ticket, state, reason=reason)
                self._save_reply(ticket_id, state, final.get("customer_reply"), user_id=ticket.get("user_id"))
                return self._finish(ticket_id, state, final, started, status="escalated")

            # ---------------- 5. Resolve ------------------------
            self.repository.update_ticket(
                ticket_id,
                status="resolved",
                assigned_agent=specialist.name,
                resolution=result.reply,
            )
            self._save_reply(ticket_id, state, result.reply, user_id=ticket.get("user_id"))
            state.status = "resolved"
            state.resolution = result.reply
            state.add_trace("Support Coordinator", "resolved", f"by {specialist.name}")
            final = {
                "success": True,
                "status": "resolved",
                "category": category,
                "confidence": confidence,
                "assigned_agent": specialist.name,
                "resolution": result.reply,
                "customer_reply": result.reply,
                "sources": result.sources,
                "agent_result": result.to_dict(),
                "escalation": {},
            }
            return self._finish(ticket_id, state, final, started, status="resolved")

        except Exception as exc:
            logger.exception("Ticket processing failed: %s", ticket_id)
            state.add_error("Support Coordinator", str(exc))
            self.repository.update_ticket(ticket_id, status="failed")
            self._log(
                ticket_id,
                "process_error",
                {"ticket_id": ticket_id},
                {"error": str(exc)[:500]},
                status="error",
                error=str(exc)[:500],
            )
            return {
                "success": False,
                "status": "failed",
                "ticket_id": ticket_id,
                "error": str(exc)[:500],
                "customer_reply": "",
                "trace": state.trace,
                "errors": state.errors,
                "retryable": True,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }

    def process_ticket_sync(self, ticket_id: str) -> dict:
        """Blocking wrapper for Streamlit and scripts."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.process_ticket(ticket_id))
        # Already inside an event loop (e.g. notebook): run in a new thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, self.process_ticket(ticket_id)).result()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _route(self, category: str, confidence: float) -> dict:
        """Routing decision executed through Semantic Kernel (with fallback)."""
        try:
            result = await self.kernel.invoke(
                plugin_name="routing_tools",
                function_name="route_ticket",
                arguments=KernelArguments(category=category, confidence=confidence),
            )
            data = json.loads(str(result))
            if isinstance(data, dict) and "next_agent" in data:
                return data
        except Exception as exc:
            logger.debug("SK routing invocation failed (%s); using direct routing", exc)
        return route_ticket(category, confidence)

    def _agent_for(self, agent_name: Optional[str]):
        return {
            AGENT_BILLING: self.billing,
            AGENT_TECHNICAL: self.technical,
            AGENT_ACCOUNT: self.account,
            AGENT_ESCALATION: self.escalation,
        }.get(agent_name)

    async def _escalate(self, ticket: dict, state: SharedTicketState, reason: str) -> dict:
        state.escalation_reason = reason or "Human review required."
        state.add_trace("Support Coordinator", "escalate", state.escalation_reason)
        escalation = await self.escalation.run(ticket, state)
        state.escalation = escalation.to_dict()
        state.status = "escalated"
        state.resolution = state.escalation_reason
        self.repository.update_ticket(
            ticket["id"],
            status="escalated",
            assigned_agent="Human Support Queue",
            resolution=state.escalation_reason,
        )
        self._save_reply(
            ticket["id"], state, escalation.reply, user_id=ticket.get("user_id")
        )
        return {
            "success": escalation.success,
            "status": "escalated",
            "category": state.category,
            "confidence": state.confidence,
            "assigned_agent": "Human Support Queue",
            "resolution": state.escalation_reason,
            "customer_reply": escalation.reply,
            "sources": [],
            "escalation": escalation.output.get("escalation", {}),
            "agent_result": escalation.to_dict(),
        }

    def _save_reply(self, ticket_id: str, state: SharedTicketState, reply: Optional[str], user_id=None) -> None:
        if reply:
            try:
                self.memory.add_assistant_message(ticket_id, reply, user_id=user_id)
            except Exception as exc:
                logger.warning("Could not save assistant reply: %s", exc)

    def _finish(self, ticket_id: str, state: SharedTicketState, final: dict, started: float, status: str) -> dict:
        state.status = status
        duration_ms = int((time.perf_counter() - started) * 1000)
        self._log(
            ticket_id,
            "process_complete",
            {"ticket_id": ticket_id},
            {
                "status": status,
                "category": final.get("category"),
                "assigned_agent": final.get("assigned_agent"),
                "duration_ms": duration_ms,
            },
        )
        return {
            **final,
            "ticket_id": ticket_id,
            "trace": state.trace,
            "errors": state.errors,
            "classification": state.classification,
            "duration_ms": duration_ms,
        }

    def _log(self, ticket_id, action, input_data=None, output_data=None, status="success", error=None):
        try:
            self.repository.log_agent(
                ticket_id=ticket_id,
                agent_name="Support Coordinator",
                action=action,
                input_data=input_data or {},
                output_data=output_data or {},
                status=status,
                error=error,
            )
        except Exception as exc:
            logger.warning("Coordinator log failed: %s", exc)

    # ------------------------------------------------------------------
    # Roster used by /agents and the dashboard
    # ------------------------------------------------------------------
    def get_agent_roster(self) -> list[dict]:
        agents = [
            self.classifier,
            self.billing,
            self.technical,
            self.account,
            self.escalation,
        ]
        roster = []
        for agent in agents:
            direct = getattr(agent.plugin, "direct", {}) if agent.plugin else {}
            roster.append(
                {
                    "name": agent.name,
                    "description": agent.description,
                    "responsibilities": agent.responsibilities,
                    "tools": sorted(direct.keys()),
                    "status": "active" if agent.groq.available else "degraded",
                }
            )
        return roster
