"""TEST 3 - Escalation scenario.

An unclear complaint must fall below 70% confidence, activate the Escalation
Router, create an escalation record and later be resolved by a human verdict.
"""

from __future__ import annotations

import pytest

from agents.escalation_agent import EscalationAgent
from memory.conversation_memory import ConversationMemory
from orchestration.routing import route_ticket


def test_routing_low_confidence_escalates():
    decision = route_ticket("billing", 0.55)
    assert decision["escalate"] is True
    assert decision["next_agent"] == "Escalation Router"


def test_routing_high_confidence_reaches_specialist():
    decision = route_ticket("technical", 0.92)
    assert decision["escalate"] is False
    assert decision["next_agent"] == "Technical Specialist"


@pytest.mark.asyncio
async def test_escalation_agent_creates_human_queue_entry(fake_repo, fake_groq):
    user = fake_repo.get_or_create_user("Confused User", "confused@example.com")
    ticket = fake_repo.create_ticket(
        user["id"],
        "Something is wrong",
        "Something feels off with my stuff. Not sure what.",
    )
    fake_repo.update_ticket(ticket["id"], confidence=0.35, category="other")
    agent = EscalationAgent(
        fake_repo, groq=fake_groq, memory=ConversationMemory(fake_repo)
    )

    result = await agent.run(fake_repo.get_ticket(ticket["id"]))

    assert result.needs_escalation is True
    assert result.success is True
    escalation = fake_repo.get_escalation_by_ticket(ticket["id"])
    assert escalation is not None
    assert escalation["status"] == "pending"
    assert escalation["priority"] in ("high", "urgent")
    assert fake_repo.get_ticket(ticket["id"])["status"] == "escalated"
    assert "create_escalation_ticket" in result.used_tools
    assert "check_escalation_status" in result.used_tools


@pytest.mark.asyncio
async def test_human_verdict_resolves_ticket(fake_repo, fake_groq):
    user = fake_repo.get_or_create_user("Verdict User", "verdict@example.com")
    ticket = fake_repo.create_ticket(user["id"], "Unclear", "Not sure about my request.")
    fake_repo.update_ticket(ticket["id"], confidence=0.4, category="other")
    agent = EscalationAgent(
        fake_repo, groq=fake_groq, memory=ConversationMemory(fake_repo)
    )
    await agent.run(fake_repo.get_ticket(ticket["id"]))
    escalation = fake_repo.get_escalation_by_ticket(ticket["id"])

    outcome = agent.process_human_verdict(
        escalation_id=escalation["id"],
        verdict="Customer contacted by phone; issue clarified as a general question.",
        resolution="Answered the customer's question directly by email.",
        operator="Human Support",
        action="resolve",
    )

    assert outcome["ticket_status"] == "resolved"
    assert fake_repo.get_ticket(ticket["id"])["status"] == "resolved"
    assert fake_repo.get_escalation(escalation["id"])["human_verdict"]
    human_logs = [l for l in fake_repo.logs if l["agent_name"] == "Human Support"]
    assert any(l["action"] == "human_verdict" for l in human_logs)
    history = fake_repo.get_conversation(ticket["id"])
    assert any(m["role"] == "human_support" for m in history)


@pytest.mark.asyncio
async def test_human_reject_reopens_ticket(fake_repo, fake_groq):
    user = fake_repo.get_or_create_user("Reject User", "reject@example.com")
    ticket = fake_repo.create_ticket(user["id"], "Unclear", "Not sure about my request.")
    fake_repo.update_ticket(ticket["id"], confidence=0.4, category="other")
    agent = EscalationAgent(
        fake_repo, groq=fake_groq, memory=ConversationMemory(fake_repo)
    )
    await agent.run(fake_repo.get_ticket(ticket["id"]))
    escalation = fake_repo.get_escalation_by_ticket(ticket["id"])

    outcome = agent.process_human_verdict(
        escalation_id=escalation["id"],
        verdict="Proposed resolution rejected - needs more evidence.",
        action="reject",
    )

    assert outcome["ticket_status"] == "open"
    assert fake_repo.get_escalation(escalation["id"])["status"] == "rejected"


def test_invalid_action_is_rejected(fake_repo, fake_groq):
    agent = EscalationAgent(fake_repo, groq=fake_groq)
    with pytest.raises(ValueError):
        agent.process_human_verdict("missing-id", "verdict", action="delete_everything")
