"""Database tests.

Unit tests validate the migration files and configuration handling without
needing a database. The live CRUD test runs only when DATABASE_URL is set -
it is SKIPPED (not passed) otherwise.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from database.connection import (
    DatabaseNotConfiguredError,
    check_database_connection,
    get_engine,
    reset_engine_cache,
)
from llm.model_config import get_settings

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "database" / "migrations"

LIVE_DB = bool(os.getenv("DATABASE_URL", "").strip())


def _clear_config_caches():
    get_settings.cache_clear()
    reset_engine_cache()


def test_migration_files_exist():
    names = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    assert names == [
        "001_initial_schema.sql",
        "002_vector_search.sql",
        "003_security_policies.sql",
    ]


def test_initial_schema_contains_all_tables():
    sql = (MIGRATIONS / "001_initial_schema.sql").read_text(encoding="utf-8").lower()
    for table in [
        "users", "tickets", "conversations", "agent_logs",
        "knowledge_documents", "escalations",
    ]:
        assert f"create table if not exists {table}" in sql
    assert "vector(384)" in sql
    assert "create extension if not exists vector" in sql
    assert "append" in sql  # append-only trigger


def test_vector_search_function_defined():
    sql = (MIGRATIONS / "002_vector_search.sql").read_text(encoding="utf-8").lower()
    assert "create or replace function match_knowledge_chunks" in sql
    assert "<=>" in sql


def test_security_policies_enable_rls():
    sql = (MIGRATIONS / "003_security_policies.sql").read_text(encoding="utf-8").lower()
    assert sql.count("enable row level security") >= 6
    assert "create policy" in sql


def test_missing_database_url_raises_helpful_error(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    _clear_config_caches()
    try:
        with pytest.raises(DatabaseNotConfiguredError):
            get_engine()
        ok, message = check_database_connection()
        assert ok is False
        assert "DATABASE_URL" in message
    finally:
        _clear_config_caches()


def test_update_whitelist_blocks_unknown_fields():
    from database.repository import Repository

    assert "status" in Repository._TICKET_FIELDS
    assert "resolution" in Repository._TICKET_FIELDS
    assert "password" not in Repository._TICKET_FIELDS
    assert "id" not in Repository._TICKET_FIELDS


@pytest.mark.skipif(not LIVE_DB, reason="DATABASE_URL not configured (live Supabase test)")
def test_live_database_crud():
    """Real integration test - never reported as passed when skipped."""
    from database.repository import Repository

    repo = Repository()
    assert repo.ping() is True

    suffix = uuid.uuid4().hex[:8]
    user = repo.create_user("Live Test", f"live.{suffix}@example.com")
    assert user["email"].endswith("@example.com")

    ticket = repo.create_ticket(
        user_id=user["id"],
        subject="Live integration test",
        message="Checking database CRUD end to end.",
    )
    updated = repo.update_ticket(ticket["id"], status="processing", category="other")
    assert updated["status"] == "processing"

    message = repo.add_conversation(ticket["id"], user["id"], "customer", "hello")
    assert message["role"] == "customer"
    assert len(repo.get_conversation(ticket["id"])) == 1

    log_id = repo.log_agent(ticket["id"], "Test Agent", "unit_test", {"a": 1}, {"b": 2})
    assert log_id

    escalation = repo.create_escalation(ticket["id"], "live test escalation")
    assert escalation["status"] == "pending"
    repo.update_escalation(escalation["id"], status="resolved", human_verdict="ok")
    assert repo.get_escalation(escalation["id"])["status"] == "resolved"

    repo.update_ticket(ticket["id"], status="resolved", resolution="done")
    assert repo.get_ticket(ticket["id"])["status"] == "resolved"
