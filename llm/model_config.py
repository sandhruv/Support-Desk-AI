"""Central configuration for the CSE476 Customer Support AI system.

All secrets are loaded from environment variables / a local ``.env`` file.
Nothing sensitive is ever hardcoded here.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Canonical ticket categories used across the whole system
CATEGORIES = ("billing", "technical", "account", "other")

# Display names of the specialist agents
AGENT_CLASSIFIER = "Classifier Agent"
AGENT_BILLING = "Billing Specialist"
AGENT_TECHNICAL = "Technical Specialist"
AGENT_ACCOUNT = "Account Specialist"
AGENT_ESCALATION = "Escalation Router"
AGENT_HUMAN = "Human Support"

# Confidence below this threshold forces human escalation
CONFIDENCE_THRESHOLD = 0.70

# Groq OpenAI-compatible base URL (used by the Semantic Kernel adapter)
GROQ_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"


class Settings(BaseSettings):
    """Application settings loaded from .env / process environment."""

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""

    database_url: str = ""

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    app_env: str = "development"
    api_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key.strip())

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url.strip())

    def normalized_database_url(self) -> str:
        """Return a SQLAlchemy-compatible PostgreSQL URL.

        Supabase sometimes hands out ``postgres://`` URLs which SQLAlchemy
        no longer accepts; we normalize them to ``postgresql://``.
        """
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor (safe to call from anywhere)."""
    return Settings()


def validate_configuration() -> dict:
    """Return a non-secret configuration report for /health and run.py doctor."""
    s = get_settings()
    return {
        "groq_configured": s.groq_configured,
        "groq_model": s.groq_model,
        "database_configured": s.database_configured,
        "supabase_url_configured": bool(s.supabase_url),
        "embedding_model": s.embedding_model,
        "app_env": s.app_env,
    }
