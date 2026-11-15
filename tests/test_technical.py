"""TEST 2 - Technical scenario.

"My application crashes whenever I try to log in."
Expected: classified as technical, Technical Specialist performs real RAG
searches (pgvector interface), answers are grounded in retrieved chunks and
source references are returned.
"""

from __future__ import annotations

import pytest

from agents.technical_agent import TechnicalAgent
from memory.conversation_memory import ConversationMemory
from rag.chunking import chunk_text
from tools.technical_tools import validate_technical_solution


def test_chunking_overlap_and_limits():
    text = " ".join(f"word{i}" for i in range(100))
    chunks = chunk_text(text, chunk_size=40, overlap=10)
    assert len(chunks) == 3
    assert len(chunks[0].split()) == 40
    assert chunks[0].split()[-10:] == chunks[1].split()[:10]


def test_validate_solution_flags_missing_sources():
    result = validate_technical_solution("Just restart everything and hope for the best.")
    assert result["valid"] is False or not result["grounded"]


@pytest.mark.asyncio
async def test_technical_agent_uses_rag_and_cites_sources(
    fake_repo, fake_groq, fake_retriever
):
    user = fake_repo.get_or_create_user("Tech User", "tech@example.com")
    ticket = fake_repo.create_ticket(
        user["id"],
        "App crashes on login",
        "My application crashes whenever I try to log in on Android 14.",
    )
    agent = TechnicalAgent(
        fake_repo,
        groq=fake_groq,
        memory=ConversationMemory(fake_repo),
        retriever=fake_retriever,
    )

    result = await agent.run(ticket)

    assert result.success is True
    assert result.needs_escalation is False
    assert result.sources == ["technical_faq"]
    assert "technical_faq" in result.reply
    assert "search_knowledge_base" in result.used_tools
    assert "validate_technical_solution" in result.used_tools
    # RAG results are attached to the structured output
    assert result.output["search_results"][0]["similarity"] > 0.5
    assert result.output["validation"]["valid"] is True


@pytest.mark.asyncio
async def test_technical_agent_escalates_without_relevant_documents(
    fake_repo, fake_groq
):
    class EmptyRetriever:
        def retrieve(self, query, top_k=4, category=None, threshold=0.0):
            return []

        @staticmethod
        def is_sufficient(results, min_similarity=0.25):
            return False

        @staticmethod
        def format_context(results):
            return ""

        @staticmethod
        def source_titles(results):
            return []

    user = fake_repo.get_or_create_user("Tech User 2", "tech2@example.com")
    ticket = fake_repo.create_ticket(
        user["id"],
        "App crash",
        "My application crashes when I open it.",
    )
    agent = TechnicalAgent(
        fake_repo,
        groq=fake_groq,
        memory=ConversationMemory(fake_repo),
        retriever=EmptyRetriever(),
    )

    result = await agent.run(ticket)

    assert result.success is False
    assert result.needs_escalation is True
    assert "knowledge base" in result.escalation_reason.lower()


@pytest.mark.asyncio
async def test_technical_agent_escalates_on_ungrounded_answer(
    fake_repo, fake_retriever
):
    class UngroundedGroq:
        available = True

        def generate_customer_reply(self, **kwargs):
            return "Sure, just reinstall your operating system. That will fix everything."  # no sources cited

        def generate_agent_reasoning(self, *args, **kwargs):
            return ""

    user = fake_repo.get_or_create_user("Tech User 3", "tech3@example.com")
    ticket = fake_repo.create_ticket(
        user["id"], "App crash", "My application crashes on login."
    )
    agent = TechnicalAgent(
        fake_repo,
        groq=UngroundedGroq(),
        memory=ConversationMemory(fake_repo),
        retriever=fake_retriever,
    )

    result = await agent.run(ticket)

    assert result.needs_escalation is True
    assert "grounding" in result.escalation_reason.lower()
