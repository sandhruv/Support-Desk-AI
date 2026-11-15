"""TEST 1 - Billing scenario.

"My payment was deducted twice."
Expected: keyword + LLM classify as billing, Billing Specialist runs both
tools, Supabase payment records are checked, a policy-grounded reply is
generated and agent logs are saved.
"""

from __future__ import annotations

import pytest

from agents.billing_agent import BillingAgent
from memory.conversation_memory import ConversationMemory
from tools.billing_tools import (
    check_billing_policy,
    extract_transaction_reference,
)
from tools.classification_tools import keyword_classification_tool


def test_keyword_classification_detects_billing():
    result = keyword_classification_tool("My payment was deducted twice.")
    assert result["category"] == "billing"
    assert result["confidence"] >= 0.6
    assert "payment" in result["matched_keywords"]["billing"]


def test_extract_transaction_reference():
    assert extract_transaction_reference("Please check txn1001 for me") == "TXN1001"
    assert extract_transaction_reference("no reference here") is None


def test_billing_policy_topics():
    assert check_billing_policy("I was charged twice")["topic"] == "duplicate_charge"
    assert check_billing_policy("refund please")["topic"] == "refund"
    assert check_billing_policy("")["topic"] == "general"


@pytest.mark.asyncio
async def test_billing_agent_resolves_duplicate_charge(fake_repo, fake_groq, demo_ticket):
    agent = BillingAgent(fake_repo, groq=fake_groq, memory=ConversationMemory(fake_repo))

    result = await agent.run(demo_ticket)

    assert result.success is True
    assert result.agent_name == "Billing Specialist"
    assert result.needs_escalation is False
    assert result.output["payment_found"] is True
    assert result.output["transaction_ref"] == "TXN1001"
    assert len(result.output["payment_records"]) >= 1
    assert "5-7 business days" in result.reply or "refund policy" in result.reply.lower()
    # Never promise an instant refund
    assert "instant refund" not in result.reply.lower() or "no instant" in result.reply.lower()
    # Both tools executed and logged
    assert "lookup_payment_record" in result.used_tools
    assert "check_billing_policy" in result.used_tools
    actions = [log["action"] for log in fake_repo.logs if log["agent_name"] == "Billing Specialist"]
    assert "run" in actions
    assert any(action.startswith("tool:lookup_payment_record") for action in actions)


@pytest.mark.asyncio
async def test_billing_agent_escalates_missing_payment_record(fake_repo, fake_groq):
    user = fake_repo.get_or_create_user("Missing Txn", "missing@example.com")
    ticket = fake_repo.create_ticket(
        user["id"],
        "Payment taken twice",
        "I was charged twice for TXN9999. Please help.",
    )
    agent = BillingAgent(fake_repo, groq=fake_groq, memory=ConversationMemory(fake_repo))

    result = await agent.run(ticket)

    assert result.needs_escalation is True
    assert "TXN9999" in result.escalation_reason


@pytest.mark.asyncio
async def test_billing_agent_handles_unavailable_llm(fake_repo, demo_ticket):
    class OfflineGroq:
        available = False

    agent = BillingAgent(
        fake_repo, groq=OfflineGroq(), memory=ConversationMemory(fake_repo)
    )
    result = await agent.run(demo_ticket)

    assert result.success is False
    assert result.needs_escalation is True
    assert result.error is not None
