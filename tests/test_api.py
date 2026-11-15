"""API contract tests (no database or Groq credentials required)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.deps import reset_services
from database.connection import reset_engine_cache
from llm.model_config import get_settings


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    reset_engine_cache()
    reset_services()

    from api.main import app

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
    reset_engine_cache()
    reset_services()


def test_health_reports_degraded_without_database(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database_ok"] is False
    assert body["agents"] == 5
    assert "database_message" in body


def test_create_ticket_validation_rejects_bad_email(client):
    response = client.post(
        "/tickets",
        json={
            "name": "Bad Email",
            "email": "not-an-email",
            "subject": "Help",
            "message": "Something is broken here.",
        },
    )
    assert response.status_code == 422


def test_create_ticket_without_database_returns_503(client):
    response = client.post(
        "/tickets",
        json={
            "name": "Valid User",
            "email": "valid@example.com",
            "subject": "Help",
            "message": "My application crashes on login.",
        },
    )
    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]


def test_agents_roster_available_without_database(client):
    response = client.get("/agents")
    assert response.status_code == 200
    roster = response.json()
    assert len(roster) == 5
    names = {agent["name"] for agent in roster}
    assert {"Classifier Agent", "Billing Specialist", "Technical Specialist",
            "Account Specialist", "Escalation Router"} == names


def test_knowledge_requires_database(client):
    response = client.get("/knowledge")
    assert response.status_code == 503
