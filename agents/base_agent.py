"""Base class shared by all five agents.

Responsibilities handled here so each agent stays small and focused:
- Semantic Kernel creation + plugin registration
- tool execution through the kernel (with a safe direct fallback)
- append-only agent logging to Supabase
- error handling and execution timing
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from semantic_kernel.functions import KernelArguments

from llm.groq_client import GroqClient
from llm.sk_integration import build_semantic_kernel

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Structured output shared between the coordinator and agents."""

    agent_name: str
    success: bool
    output: dict = field(default_factory=dict)
    reply: str = ""
    sources: list = field(default_factory=list)
    used_tools: list = field(default_factory=list)
    needs_escalation: bool = False
    escalation_reason: str = ""
    error: Optional[str] = None
    duration_ms: int = 0
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "success": self.success,
            "output": self.output,
            "reply": self.reply,
            "sources": self.sources,
            "used_tools": self.used_tools,
            "needs_escalation": self.needs_escalation,
            "escalation_reason": self.escalation_reason,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "reasoning": self.reasoning,
        }


class BaseAgent(ABC):
    """Common behaviour for every specialist agent."""

    name: str = "Base Agent"
    description: str = ""
    responsibilities: list[str] = []
    plugin_name: str = "base_tools"

    def __init__(
        self,
        repository,
        groq: Optional[GroqClient] = None,
        memory=None,
        retriever=None,
        kernel=None,
    ):
        self.repository = repository
        self.groq = groq or GroqClient()
        self.memory = memory
        self.retriever = retriever
        self.kernel = kernel or build_semantic_kernel()
        self.plugin = self.build_plugin()
        self.used_tools: list[str] = []
        self._current_ticket_id: Optional[str] = None
        if self.plugin is not None:
            try:
                self.kernel.add_plugin(self.plugin, plugin_name=self.plugin_name)
            except Exception as exc:  # pragma: no cover - SK version guard
                logger.warning("Could not register plugin for %s: %s", self.name, exc)

    # ------------------------------------------------------------------
    # To be implemented by each agent
    # ------------------------------------------------------------------
    def build_plugin(self):
        """Return a Semantic Kernel plugin object (or None)."""
        return None

    @abstractmethod
    async def _execute(self, ticket: dict, state=None) -> AgentResult:
        """Agent-specific logic."""

    # ------------------------------------------------------------------
    # Execution wrapper: timing, logging, error containment
    # ------------------------------------------------------------------
    async def run(self, ticket: dict, state=None) -> AgentResult:
        started = time.perf_counter()
        self.used_tools = []
        self._current_ticket_id = ticket.get("id")
        try:
            result = await self._execute(ticket, state)
        except Exception as exc:
            logger.exception("%s failed", self.name)
            duration = int((time.perf_counter() - started) * 1000)
            self._log(
                ticket_id=ticket.get("id"),
                action="run",
                input_data={"ticket_id": ticket.get("id")},
                output_data={},
                status="error",
                error=str(exc)[:500],
                duration_ms=duration,
            )
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=f"{type(exc).__name__}: {exc}"[:500],
                needs_escalation=True,
                escalation_reason=f"{self.name} failed unexpectedly.",
                used_tools=list(self.used_tools),
                duration_ms=duration,
            )

        result.duration_ms = int((time.perf_counter() - started) * 1000)
        result.used_tools = list(dict.fromkeys(self.used_tools))
        self._log(
            ticket_id=ticket.get("id"),
            action="run",
            input_data={"ticket_id": ticket.get("id"), "tools": result.used_tools},
            output_data={
                "success": result.success,
                "reply_preview": (result.reply or "")[:300],
                "needs_escalation": result.needs_escalation,
                "sources": result.sources,
            },
            status="success" if result.success else "error",
            error=result.error,
            duration_ms=result.duration_ms,
        )
        return result

    # ------------------------------------------------------------------
    # Tool invocation through Semantic Kernel
    # ------------------------------------------------------------------
    async def invoke_tool(self, function_name: str, **kwargs) -> dict:
        """Execute a registered Python tool via ``kernel.invoke``.

        Falls back to calling the tool function directly if the installed
        Semantic Kernel version rejects the invocation, so tool execution
        never becomes a single point of failure.
        """
        self.used_tools.append(function_name)
        result_data: dict
        try:
            result = await self.kernel.invoke(
                plugin_name=self.plugin_name,
                function_name=function_name,
                arguments=KernelArguments(**kwargs),
            )
            raw = str(result)
            try:
                result_data = json.loads(raw)
            except json.JSONDecodeError:
                result_data = {"result": raw}
        except Exception as exc:
            direct = getattr(self.plugin, "direct", {}) if self.plugin is not None else {}
            function = direct.get(function_name)
            if function is None:
                raise
            logger.debug(
                "kernel.invoke failed for %s.%s (%s); using direct tool call",
                self.plugin_name,
                function_name,
                exc,
            )
            result_data = function(**kwargs)
            if not isinstance(result_data, dict):
                result_data = {"result": result_data}

        self._log(
            ticket_id=kwargs.get("ticket_id") or self._current_ticket_id,
            action=f"tool:{function_name}",
            input_data={
                k: (v if isinstance(v, (str, int, float, bool, list, dict)) else str(v))
                for k, v in kwargs.items()
            },
            output_data=_preview(result_data),
            status="success",
        )
        return result_data

    # ------------------------------------------------------------------
    # Logging helper (never raises - logging must not break a ticket)
    # ------------------------------------------------------------------
    def _log(
        self,
        ticket_id: Optional[str],
        action: str,
        input_data: Optional[dict] = None,
        output_data: Optional[dict] = None,
        status: str = "success",
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        try:
            self.repository.log_agent(
                ticket_id=ticket_id,
                agent_name=self.name,
                action=action,
                input_data=input_data or {},
                output_data=output_data or {},
                status=status,
                error=error,
                duration_ms=duration_ms,
            )
        except Exception as exc:  # DB down / fake repo without logging
            logger.warning("Agent log write failed (%s): %s", self.name, exc)


def _preview(data: Any, limit: int = 500) -> Any:
    """Keep log payloads small; truncate long strings recursively."""
    if isinstance(data, str):
        return data[:limit]
    if isinstance(data, list):
        return [_preview(item, limit) for item in data[:10]]
    if isinstance(data, dict):
        return {key: _preview(value, limit) for key, value in list(data.items())[:15]}
    return data
