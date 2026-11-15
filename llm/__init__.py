"""LLM package: Groq provider, configuration and prompt templates."""

from llm.groq_client import (
    GroqClient,
    GroqNotConfiguredError,
    GroqServiceError,
)
from llm.model_config import (
    AGENT_ACCOUNT,
    AGENT_BILLING,
    AGENT_CLASSIFIER,
    AGENT_ESCALATION,
    AGENT_HUMAN,
    AGENT_TECHNICAL,
    CATEGORIES,
    CONFIDENCE_THRESHOLD,
    get_settings,
)

__all__ = [
    "GroqClient",
    "GroqNotConfiguredError",
    "GroqServiceError",
    "AGENT_ACCOUNT",
    "AGENT_BILLING",
    "AGENT_CLASSIFIER",
    "AGENT_ESCALATION",
    "AGENT_HUMAN",
    "AGENT_TECHNICAL",
    "CATEGORIES",
    "CONFIDENCE_THRESHOLD",
    "get_settings",
]
