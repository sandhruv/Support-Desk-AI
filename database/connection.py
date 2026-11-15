"""Database connection layer.

The ONLY database used by this project is Supabase PostgreSQL.
This module wraps SQLAlchemy so the rest of the code never handles
connections directly. Missing configuration produces a friendly, explicit
error instead of a crash at import time.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from llm.model_config import get_settings

logger = logging.getLogger(__name__)


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when DATABASE_URL is missing from the environment."""


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create (and cache) the SQLAlchemy engine for Supabase PostgreSQL."""
    settings = get_settings()
    url = settings.normalized_database_url()
    if not url:
        raise DatabaseNotConfiguredError(
            "DATABASE_URL is not configured. Copy .env.example to .env and paste "
            "your Supabase PostgreSQL connection string (Dashboard -> Connect)."
        )
    try:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_recycle=1800,
            future=True,
            connect_args={"connect_timeout": 10},
        )
    except Exception as exc:  # malformed URL etc.
        raise DatabaseNotConfiguredError(f"Invalid DATABASE_URL: {exc}") from exc
    return engine


def reset_engine_cache() -> None:
    """Clear the cached engine (used by tests and after changing .env)."""
    try:
        get_engine.cache_clear()
    except Exception:
        pass


@contextmanager
def db_session() -> Iterator:
    """Transactional session context.

    Commits on success, rolls back on failure. All persistent data
    (tickets, conversations, logs, embeddings, escalations) lives in Supabase.
    """
    engine = get_engine()
    with engine.begin() as connection:
        yield connection


def check_database_connection() -> tuple[bool, str]:
    """Ping the database. Returns (ok, human readable message)."""
    settings = get_settings()
    if not settings.database_configured:
        return False, "DATABASE_URL is not configured (see .env.example)."
    try:
        with db_session() as conn:
            conn.execute(text("select 1"))
        return True, "Connected to Supabase PostgreSQL."
    except Exception as exc:
        return False, f"Database connection failed: {type(exc).__name__}"
