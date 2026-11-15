"""Centralised Groq Cloud client.

Every agent reuses this single service for LLM calls. The client adds:
- timeouts
- retry with exponential backoff (rate limits / transient errors)
- structured JSON responses validated with Pydantic
- token usage tracking
- safe error messages (API keys are never logged)

Groq is the ONLY LLM provider used by this project (free tier).
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any, Iterable, Optional, Type, TypeVar

from pydantic import BaseModel, Field, field_validator

from llm import prompt_templates as prompts
from llm.model_config import (
    AGENT_BILLING,
    AGENT_ESCALATION,
    CATEGORIES,
    CONFIDENCE_THRESHOLD,
    get_settings,
)

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)

# Sentinel so tests can inject a fake Groq SDK client
_UNSET = object()


class GroqNotConfiguredError(RuntimeError):
    """Raised when GROQ_API_KEY is missing."""


class GroqServiceError(RuntimeError):
    """Raised when Groq returned an unrecoverable error.

    ``retryable`` tells callers (e.g. the API layer) that the ticket should be
    kept and retried later instead of being marked failed.
    """

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


# ---------------------------------------------------------------------------
# Pydantic models for structured LLM output
# ---------------------------------------------------------------------------
class ClassificationLLMResponse(BaseModel):
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    issue: str = ""
    reasoning: str = ""

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        value = (value or "").strip().lower()
        aliases = {
            "payments": "billing",
            "payment": "billing",
            "billing_issue": "billing",
            "tech": "technical",
            "technical_issue": "technical",
            "login": "account",
            "access": "account",
            "account_issue": "account",
            "general": "other",
        }
        value = aliases.get(value, value)
        if value not in CATEGORIES:
            raise ValueError(f"Invalid category '{value}'")
        return value


class ReasoningResponse(BaseModel):
    reasoning: str = ""


class SummaryResponse(BaseModel):
    summary: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> dict:
    """Extract the first JSON object from an LLM response."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise GroqServiceError("LLM did not return valid JSON.", retryable=True)
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise GroqServiceError("LLM returned malformed JSON.", retryable=True) from exc
    if not isinstance(data, dict):
        raise GroqServiceError("LLM JSON was not an object.", retryable=True)
    return data


class GroqClient:
    """Shared Groq LLM service used by all agents."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 45.0,
        max_retries: int = 3,
        client: Any = _UNSET,
    ) -> None:
        settings = get_settings()
        self.api_key = (api_key if api_key is not None else settings.groq_api_key) or ""
        self.model = model or settings.groq_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.usage = {
            "requests": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        if client is not _UNSET:
            self._client = client  # injected (tests / notebooks)
        elif self.api_key.strip():
            from groq import Groq  # imported lazily so tests need no network deps

            self._client = Groq(api_key=self.api_key.strip(), timeout=timeout)
        else:
            self._client = None

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._client is not None

    def require_available(self) -> None:
        if not self.available:
            raise GroqNotConfiguredError(
                "GROQ_API_KEY is not configured. Add it to your .env file "
                "(see .env.example) and restart the app."
            )

    def get_usage(self) -> dict:
        return dict(self.usage)

    def list_models(self) -> list[str]:
        """Return model IDs available to this Groq account (free tier aware)."""
        self.require_available()
        try:
            response = self._client.models.list()
            return sorted(m.id for m in response.data)
        except Exception as exc:  # pragma: no cover - network dependent
            raise GroqServiceError(f"Could not list Groq models: {exc}") from exc

    # ------------------------------------------------------------------
    # Low level chat completion with retries
    # ------------------------------------------------------------------
    def _chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        self.require_available()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                response = self._client.chat.completions.create(**kwargs)
                self.usage["requests"] += 1
                usage = getattr(response, "usage", None)
                if usage is not None:
                    self.usage["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
                    self.usage["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
                    self.usage["total_tokens"] += getattr(usage, "total_tokens", 0) or 0
                content = response.choices[0].message.content or ""
                # Normalise exotic unicode spaces that break some consoles/logs
                content = (
                    content.replace("\u202f", " ")
                    .replace("\u00a0", " ")
                    .replace("\u2009", " ")
                    .strip()
                )
                return content
            except Exception as exc:  # classify below
                last_error = exc
                self.usage["errors"] += 1
                if not self._is_retryable(exc) or attempt >= self.max_retries:
                    break
                delay = min(2 ** attempt + random.uniform(0, 0.4), 12)
                logger.warning(
                    "Groq request failed (attempt %s/%s): %s - retrying in %.1fs",
                    attempt + 1,
                    self.max_retries + 1,
                    type(exc).__name__,
                    delay,
                )
                time.sleep(delay)

        raise GroqServiceError(
            self._friendly_error(last_error), retryable=self._is_retryable(last_error)
        )

    @staticmethod
    def _is_retryable(exc: Optional[Exception]) -> bool:
        if exc is None:
            return False
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        if "ratelimit" in name or "rate limit" in text or "429" in text:
            return True
        if "timeout" in name or "connection" in name:
            return True
        status = getattr(exc, "status_code", None)
        if isinstance(status, int) and (status == 429 or status >= 500):
            return True
        return False

    @staticmethod
    def _friendly_error(exc: Optional[Exception]) -> str:
        if exc is None:
            return "Groq request failed for an unknown reason. The ticket was kept for retry."
        name = type(exc).__name__.lower()
        text = str(exc)
        status = getattr(exc, "status_code", None)
        if (
            "ratelimit" in name
            or "rate limit" in text.lower()
            or status == 429
            or "429" in text
        ):
            return (
                "Groq free-tier rate limit reached. Please wait a moment and retry - "
                "the ticket has been preserved."
            )
        if "timeout" in name or "connection" in name:
            return "Could not reach Groq. Check your internet connection and retry."
        if "401" in text or "invalid api key" in text.lower() or "authentication" in name:
            return "Groq authentication failed. Verify GROQ_API_KEY in your .env file."
        if "model" in text.lower() and ("not found" in text.lower() or "does not exist" in text.lower()):
            return "The configured GROQ_MODEL is not available on this account. Choose another free-tier model."
        return f"Groq request failed: {type(exc).__name__}."

    # ------------------------------------------------------------------
    # Public generation API
    # ------------------------------------------------------------------
    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        """Generate a plain text (or JSON mode) response from Groq."""
        return self._chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    def generate_structured_response(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[TModel],
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> TModel:
        """Generate JSON and validate it against a Pydantic schema.

        If the first answer is invalid, one repair attempt is made.
        """
        schema_hint = json.dumps(schema.model_json_schema(), indent=None)
        user_prompt = (
            f"{user_prompt}\n\nReturn ONLY valid JSON matching this JSON schema:\n{schema_hint}"
        )
        raw = self.generate_response(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            return schema.model_validate(_extract_json(raw))
        except Exception as first_error:
            repair = (
                f"{user_prompt}\n\nYour previous answer was invalid: {first_error}\n"
                "Return ONLY corrected JSON."
            )
            raw2 = self.generate_response(
                system_prompt,
                repair,
                temperature=0.0,
                max_tokens=max_tokens,
                json_mode=True,
            )
            try:
                return schema.model_validate(_extract_json(raw2))
            except Exception as exc:
                raise GroqServiceError(
                    "The LLM response failed validation. Please retry.", retryable=True
                ) from exc

    # ------------------------------------------------------------------
    # Convenience methods used by the agents
    # ------------------------------------------------------------------
    def classify_ticket(self, message: str, subject: str = "") -> dict:
        """Classify a support ticket into billing/technical/account/other."""
        result = self.generate_structured_response(
            prompts.CLASSIFIER_SYSTEM,
            prompts.CLASSIFIER_USER.format(subject=subject, message=message),
            ClassificationLLMResponse,
            temperature=0.0,
        )
        agent_map = {
            "billing": AGENT_BILLING,
            "technical": "Technical Specialist",
            "account": "Account Specialist",
            "other": AGENT_ESCALATION,
        }
        return {
            "category": result.category,
            "confidence": round(float(result.confidence), 3),
            "issue": result.issue or "Unspecified issue",
            "reasoning": result.reasoning,
            "assigned_agent": agent_map.get(result.category, AGENT_ESCALATION),
            "needs_escalation": result.confidence < CONFIDENCE_THRESHOLD
            or result.category == "other",
        }

    def generate_customer_reply(
        self,
        agent_name: str,
        subject: str,
        message: str,
        evidence: str,
        category: str = "other",
        history: str = "",
    ) -> str:
        """Compose the customer-facing reply grounded in tool evidence."""
        return self.generate_response(
            prompts.customer_reply_system(agent_name),
            prompts.REPLY_USER.format(
                agent_name=agent_name,
                subject=subject,
                message=message,
                category=category,
                evidence=evidence or "No tool evidence available.",
                history=history or "No previous conversation.",
            ),
            temperature=0.25,
            max_tokens=600,
        )

    def summarize_conversation(self, history: str) -> str:
        """Summarise a conversation (persistent memory helper)."""
        result = self.generate_structured_response(
            prompts.SUMMARIZER_SYSTEM,
            f"Conversation:\n{history}",
            SummaryResponse,
            temperature=0.2,
            max_tokens=300,
        )
        return result.summary

    def generate_agent_reasoning(self, agent_name: str, situation: str) -> str:
        """Generate the short reasoning summary shown on the dashboard."""
        try:
            result = self.generate_structured_response(
                prompts.reasoning_system(agent_name),
                situation,
                ReasoningResponse,
                temperature=0.2,
                max_tokens=220,
            )
            return result.reasoning
        except GroqServiceError:
            return ""
