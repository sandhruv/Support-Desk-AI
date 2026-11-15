"""Real integration tests - only run when credentials are configured.

These tests are SKIPPED (never falsely reported as passed) when
GROQ_API_KEY / DATABASE_URL are missing.
"""

from __future__ import annotations

import os

import pytest

GROQ_LIVE = bool(os.getenv("GROQ_API_KEY", "").strip())
DB_LIVE = bool(os.getenv("DATABASE_URL", "").strip())


@pytest.mark.skipif(not GROQ_LIVE, reason="GROQ_API_KEY not configured (live test)")
def test_groq_live_connectivity_and_model_availability():
    from llm.groq_client import GroqClient

    client = GroqClient()
    models = client.list_models()
    assert len(models) > 0, "No models returned by Groq for this account"
    print(f"\nGroq models available ({len(models)}): {models[:10]}")

    from llm.model_config import get_settings

    configured = get_settings().groq_model
    if configured not in models:
        print(f"WARNING: configured model '{configured}' not in account model list")


@pytest.mark.skipif(not GROQ_LIVE, reason="GROQ_API_KEY not configured (live test)")
def test_groq_live_structured_classification():
    from llm.groq_client import GroqClient

    client = GroqClient()
    result = client.classify_ticket("My payment was deducted twice.", "Billing issue")
    assert result["category"] == "billing"
    assert 0.0 <= result["confidence"] <= 1.0


@pytest.mark.skipif(not DB_LIVE, reason="DATABASE_URL not configured (live test)")
def test_supabase_live_ping():
    from database.repository import Repository

    assert Repository().ping() is True


@pytest.mark.skipif(
    not (DB_LIVE and os.getenv("RUN_EMBEDDING_TESTS")),
    reason="Live embedding test requires DATABASE_URL and RUN_EMBEDDING_TESTS=1",
)
def test_live_rag_ingest_and_search():
    """Heavy test: downloads all-MiniLM-L6-v2 and writes to pgvector."""
    from database.repository import Repository
    from rag.ingestion import KnowledgeIngestion
    from rag.retriever import KnowledgeRetriever

    repo = Repository()
    ingestion = KnowledgeIngestion(repo)
    result = ingestion.ingest_directory()
    assert result["documents"] >= 5
    assert result["chunks"] > 0

    retriever = KnowledgeRetriever(repo)
    results = retriever.retrieve("application crashes during login", top_k=3)
    assert len(results) > 0
    assert results[0]["title"]
