"""Semantic Kernel integration.

The project uses Microsoft Semantic Kernel as the agent framework:

* A ``Kernel`` is created per agent.
* Every agent registers its Python tools as Semantic Kernel plugins
  (``kernel.add_plugin``); tools are executed through ``kernel.invoke``.
* Groq is integrated through the OpenAI-compatible endpoint
  (``https://api.groq.com/openai/v1``) using the OpenAI async client that
  Semantic Kernel's connector accepts.
* Structured LLM generation flows through the central Groq SDK client
  (``llm/groq_client.py``), which all agents share.

If the connector cannot be configured, the kernel is still created with
plugins so tool execution keeps working, and a warning is logged.
"""

from __future__ import annotations

import logging
from typing import Optional

from semantic_kernel import Kernel

from llm.model_config import GROQ_OPENAI_BASE_URL, get_settings

logger = logging.getLogger(__name__)


def build_semantic_kernel() -> Kernel:
    """Create a Semantic Kernel wired to Groq (OpenAI-compatible endpoint)."""
    kernel = Kernel()
    settings = get_settings()
    if not settings.groq_configured:
        logger.info("GROQ_API_KEY not set - Kernel created without a chat service.")
        return kernel

    try:
        from openai import AsyncOpenAI
        from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

        async_client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=GROQ_OPENAI_BASE_URL,
            timeout=45.0,
        )
        chat_service = OpenAIChatCompletion(
            ai_model_id=settings.groq_model,
            async_client=async_client,
            service_id="groq_chat",
        )
        kernel.add_service(chat_service)
        logger.info("Semantic Kernel chat service registered (Groq endpoint).")
    except Exception as exc:  # pragma: no cover - version dependent
        logger.warning("Could not register SK chat service: %s", exc)

    return kernel


def get_chat_service(kernel: Optional[Kernel] = None):
    """Return the Groq-backed chat service from a kernel (or None)."""
    kernel = kernel or build_semantic_kernel()
    try:
        return kernel.get_service(service_id="groq_chat")
    except Exception:
        return None
