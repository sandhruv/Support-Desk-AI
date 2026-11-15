"""Orchestration tests - the full multi-agent pipeline with deterministic fakes."""

from __future__ import annotations

import pytest

from llm.groq_client import GroqClient, GroqServiceError, _extract_json
from memory.conversation_memory import ConversationMemory
from orchestration.coordinator import SupportCoordinator, TicketNotFoundError


def make_coordinator(fake_repo, fake_groq, fake_retriever=None):
    return SupportCoordinator(
        repository=fake_repo,
        groq=fake_groq,
        retriever=fake_retriever,
    )


@pytest.mark.asyncio
async def test_billing_ticket_full_pipeline(fake_repo, fake_groq):
    coordinator = make_coordinator(fake_repo, fake_groq)
    user = fake_repo.get_or_create_user("Pipeline User", "pipeline@example.com")
    fake_repo.add_payment(user["id"], "TXN1001", 49.99, "completed", "Pro plan")
    fake_repo.add_payment(user["id"], "TXN1002", 49.99, "completed", "Pro plan duplicate")
    ticket = fake_repo.create_ticket(
        user["id"],
        "My payment was deducted twice",
        "I was charged twice for TXN1001. Please refund the duplicate charge.",
        priority="high",
    )
    fake_repo.add_conversation(ticket["id"], user["id"], "customer", ticket["message"])

    result = await coordinator.process_ticket(ticket["id"])

    assert result["status"] == "resolved"
    assert result["category"] == "billing"
    assert result["assigned_agent"] == "Billing Specialist"
    assert fake_repo.get_ticket(ticket["id"])["status"] == "resolved"

    trace_agents = [step["agent"] for step in result["trace"]]
    assert "Classifier Agent" in trace_agents
    assert "Billing Specialist" in trace_agents

    history = fake_repo.get_conversation(ticket["id"])
    assert any(m["role"] == "assistant" and m["message"] for m in history)
    assert any(log["agent_name"] == "Support Coordinator" for log in fake_repo.logs)


@pytest.mark.asyncio
async def test_technical_ticket_uses_rag(fake_repo, fake_groq, fake_retriever):
    coordinator = make_coordinator(fake_repo, fake_groq, fake_retriever)
    user = fake_repo.get_or_create_user("Tech Pipeline", "techpipe@example.com")
    ticket = fake_repo.create_ticket(
        user["id"],
        "App crashes on login",
        "My application crashes whenever I try to log in.",
    )
    fake_repo.add_conversation(ticket["id"], user["id"], "customer", ticket["message"])

    result = await coordinator.process_ticket(ticket["id"])

    assert result["status"] == "resolved"
    assert result["category"] == "technical"
    assert result["assigned_agent"] == "Technical Specialist"
    assert "technical_faq" in result["sources"]


@pytest.mark.asyncio
async def test_unclear_ticket_escalates_and_human_resolves(fake_repo, fake_groq):
    coordinator = make_coordinator(fake_repo, fake_groq)
    user = fake_repo.get_or_create_user("Escalate Pipeline", "escpipeline@example.com")
    ticket = fake_repo.create_ticket(
        user["id"],
        "Not sure",
        "Something feels off with my stuff. Not sure what.",
    )
    fake_repo.add_conversation(ticket["id"], user["id"], "customer", ticket["message"])

    result = await coordinator.process_ticket(ticket["id"])

    assert result["status"] == "escalated"
    assert result["confidence"] < 0.70
    escalation = fake_repo.get_escalation_by_ticket(ticket["id"])
    assert escalation and escalation["status"] == "pending"
    assert fake_repo.get_ticket(ticket["id"])["status"] == "escalated"

    # Human-in-the-loop finishes the ticket
    verdict = coordinator.escalation.process_human_verdict(
        escalation_id=escalation["id"],
        verdict="Contacted the customer; resolved manually.",
        resolution="Explained the account status by email.",
        action="resolve",
    )
    assert verdict["ticket_status"] == "resolved"


@pytest.mark.asyncio
async def test_unknown_ticket_raises(fake_repo, fake_groq):
    coordinator = make_coordinator(fake_repo, fake_groq)
    with pytest.raises(TicketNotFoundError):
        await coordinator.process_ticket("00000000-0000-0000-0000-000000000000")


def test_coordinator_roster_has_five_agents(fake_repo, fake_groq):
    coordinator = make_coordinator(fake_repo, fake_groq)
    roster = coordinator.get_agent_roster()
    assert len(roster) == 5
    tools = {agent["name"]: agent["tools"] for agent in roster}
    assert len(tools["Billing Specialist"]) >= 2
    assert len(tools["Technical Specialist"]) >= 2
    assert len(tools["Account Specialist"]) >= 2
    assert len(tools["Escalation Router"]) >= 2
    assert len(tools["Classifier Agent"]) >= 2


# ---------------------------------------------------------------------------
# Groq client robustness (no network)
# ---------------------------------------------------------------------------
def test_extract_json_from_fenced_response():
    assert _extract_json('```json\n{"category": "billing"}\n```') == {
        "category": "billing"
    }
    assert _extract_json('prefix {"a": 1} suffix') == {"a": 1}


def test_groq_client_retries_then_fails(monkeypatch):
    class FakeStatusError(Exception):
        status_code = 429

    calls = {"count": 0}

    class FakeCompletions:
        def create(self, **kwargs):
            calls["count"] += 1
            raise FakeStatusError("rate limited")

    class FakeChat:
        completions = FakeCompletions()

    class FakeSDK:
        chat = FakeChat()

    monkeypatch.setattr("time.sleep", lambda *_: None)
    client = GroqClient(api_key="test-key", client=FakeSDK(), max_retries=2)

    with pytest.raises(GroqServiceError) as excinfo:
        client.generate_response("system", "user")

    assert excinfo.value.retryable is True
    assert "rate limit" in str(excinfo.value).lower()
    assert calls["count"] == 3  # initial + 2 retries
    assert client.usage["errors"] >= 3


def test_groq_unconfigured_raises_helpful_error(monkeypatch):
    from llm.groq_client import GroqNotConfiguredError

    client = GroqClient(api_key="", client=None, model="llama-3.3-70b-versatile")
    # client=None marks _client explicitly, but api_key empty must still fail
    with pytest.raises(GroqNotConfiguredError):
        client.require_available()
