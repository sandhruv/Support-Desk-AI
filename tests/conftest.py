"""Shared pytest fixtures: fake repository and fake Groq client.

Unit tests are fully deterministic and need no network, database or API key.
Real integrations are tested separately in test_integration_live.py.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover
    pass


class FakeRepository:
    """In-memory stand-in that mimics the Repository interface used by agents."""

    def __init__(self):
        self.users = {}
        self.tickets = {}
        self.conversations = []
        self.logs = []
        self.escalations = {}
        self.payments = []

    # -- users ---------------------------------------------------------
    def create_user(self, name, email):
        user = {
            "id": str(uuid.uuid4()), "name": name, "email": email.lower(),
        }
        self.users[user["id"]] = user
        return user

    def get_or_create_user(self, name, email):
        for user in self.users.values():
            if user["email"] == email.lower():
                return user
        return self.create_user(name, email)

    def get_user(self, user_id):
        return self.users.get(str(user_id))

    def get_user_by_email(self, email):
        for user in self.users.values():
            if user["email"] == (email or "").lower():
                return user
        return None

    # -- tickets -------------------------------------------------------
    def create_ticket(self, user_id, subject, message, priority="medium"):
        ticket = {
            "id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "subject": subject,
            "message": message,
            "category": None,
            "confidence": None,
            "status": "open",
            "assigned_agent": None,
            "resolution": None,
            "priority": priority,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        self.tickets[ticket["id"]] = ticket
        return dict(ticket)

    def get_ticket(self, ticket_id):
        ticket = self.tickets.get(str(ticket_id))
        return dict(ticket) if ticket else None

    def list_tickets(self, category=None, status=None, priority=None, search=None, limit=200):
        results = list(self.tickets.values())
        if search:
            results = [
                t for t in results
                if search.lower() in t["subject"].lower()
                or search.lower() in t["message"].lower()
                or search.lower() in self.users.get(t["user_id"], {}).get("email", "").lower()
            ]
        return [dict(t) for t in results[:limit]]

    def update_ticket(self, ticket_id, **fields):
        ticket = self.tickets.get(str(ticket_id))
        if not ticket:
            return None
        allowed = {"category", "confidence", "status", "assigned_agent",
                   "resolution", "priority", "subject", "message"}
        for key, value in fields.items():
            if key in allowed:
                ticket[key] = value
        return dict(ticket)

    # -- conversations -------------------------------------------------
    def add_conversation(self, ticket_id, user_id, role, message):
        item = {
            "id": str(uuid.uuid4()),
            "ticket_id": str(ticket_id),
            "user_id": str(user_id) if user_id else None,
            "role": role,
            "message": message,
            "created_at": "2026-01-01T00:00:00Z",
        }
        self.conversations.append(item)
        return dict(item)

    def get_conversation(self, ticket_id):
        return [c for c in self.conversations if c["ticket_id"] == str(ticket_id)]

    # -- logs ----------------------------------------------------------
    def log_agent(self, ticket_id, agent_name, action, input_data=None,
                  output_data=None, status="success", error=None, duration_ms=None):
        log_id = str(uuid.uuid4())
        self.logs.append({
            "id": log_id,
            "ticket_id": ticket_id,
            "agent_name": agent_name,
            "action": action,
            "input_data": input_data or {},
            "output_data": output_data or {},
            "execution_status": status,
            "error_message": error,
            "duration_ms": duration_ms,
        })
        return log_id

    def list_agent_logs(self, ticket_id=None, agent_name=None, limit=200):
        logs = self.logs
        if ticket_id:
            logs = [l for l in logs if l["ticket_id"] == str(ticket_id)]
        if agent_name:
            logs = [l for l in logs if l["agent_name"] == agent_name]
        return logs[-limit:]

    # -- payments ------------------------------------------------------
    def add_payment(self, user_id, transaction_ref, amount, status, description):
        record = {
            "id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "transaction_ref": transaction_ref,
            "amount": amount,
            "status": status,
            "description": description,
            "currency": "USD",
        }
        self.payments.append(record)
        return dict(record)

    def lookup_payment_records(self, user_id=None, transaction_ref=None):
        results = self.payments
        if user_id:
            results = [p for p in results if p["user_id"] == str(user_id)]
        if transaction_ref:
            results = [p for p in results
                       if p["transaction_ref"].upper() == transaction_ref.upper()]
        return [dict(p) for p in results]

    # -- escalations ---------------------------------------------------
    def create_escalation(self, ticket_id, reason, priority="high",
                          assigned_to="Human Support Queue"):
        escalation = {
            "id": str(uuid.uuid4()),
            "ticket_id": str(ticket_id),
            "reason": reason,
            "priority": priority,
            "assigned_to": assigned_to,
            "status": "pending",
            "human_verdict": None,
            "created_at": "2026-01-01T00:00:00Z",
            "resolved_at": None,
        }
        self.escalations[escalation["id"]] = escalation
        return dict(escalation)

    def get_escalation(self, escalation_id):
        found = self.escalations.get(str(escalation_id))
        return dict(found) if found else None

    def get_escalation_by_ticket(self, ticket_id):
        for escalation in reversed(list(self.escalations.values())):
            if escalation["ticket_id"] == str(ticket_id):
                return dict(escalation)
        return None

    def update_escalation(self, escalation_id, **fields):
        escalation = self.escalations.get(str(escalation_id))
        if not escalation:
            return None
        allowed = {"status", "human_verdict", "assigned_to", "priority", "reason"}
        for key, value in fields.items():
            if key in allowed:
                escalation[key] = value
        if fields.get("status") in ("resolved", "rejected"):
            escalation["resolved_at"] = "2026-01-01T01:00:00Z"
        return dict(escalation)


class FakeGroq:
    """Deterministic stand-in for GroqClient (no network calls)."""

    available = True

    def __init__(self):
        self.calls = []

    def classify_ticket(self, message, subject=""):
        self.calls.append(("classify", message))
        text = f"{subject} {message}".lower()
        if any(w in text for w in ("payment", "charged", "deducted", "refund", "twice", "txn")):
            return {
                "category": "billing", "confidence": 0.95,
                "issue": "Duplicate payment", "reasoning": "Billing keywords detected.",
                "assigned_agent": "Billing Specialist", "needs_escalation": False,
            }
        if any(w in text for w in ("crash", "login", "error", "bug", "app")):
            return {
                "category": "technical", "confidence": 0.90,
                "issue": "Application crash on login", "reasoning": "Technical keywords detected.",
                "assigned_agent": "Technical Specialist", "needs_escalation": False,
            }
        if any(w in text for w in ("password", "account", "access", "reset")):
            return {
                "category": "account", "confidence": 0.88,
                "issue": "Account access problem", "reasoning": "Account keywords detected.",
                "assigned_agent": "Account Specialist", "needs_escalation": False,
            }
        return {
            "category": "other", "confidence": 0.35,
            "issue": "Unclear request", "reasoning": "No clear category signal.",
            "assigned_agent": "Escalation Router", "needs_escalation": True,
        }

    def generate_customer_reply(self, agent_name, subject, message, evidence,
                                category="other", history=""):
        self.calls.append(("reply", agent_name, evidence[:200]))
        import re

        source = re.search(r"\[Source: ([^\]]+)\]", evidence or "")
        if source:
            title = source.group(1)
            passage = (evidence or "").replace("[Source: " + title + "]", "")
            return (
                f"Thanks for contacting support. Based on {title}, here is what "
                f"we recommend: {passage[:220].strip()} If this does not help, "
                f"reply here and we will escalate your case."
            )
        if category == "billing":
            return (
                "Thanks for your patience. I checked your payment records and the "
                "billing policy. The duplicate charge is being reviewed under our "
                "refund policy and will be returned to the original payment method "
                "within 5-7 business days if confirmed. No instant refund is promised."
            )
        if category == "account":
            return (
                "Please use the 'Forgot password' link on the login page. The reset "
                "link expires after 30 minutes. If you still cannot access your "
                "account, we will verify your identity before unlocking it."
            )
        return "Thank you for your message. A support specialist is reviewing your case."

    def generate_agent_reasoning(self, agent_name, situation):
        self.calls.append(("reasoning", agent_name))
        return f"{agent_name} checked the available tool evidence before replying."

    def generate_response(self, system_prompt, user_prompt, temperature=0.3, max_tokens=1024, json_mode=False):
        self.calls.append(("response", user_prompt[:120]))
        return "The ticket needs human review because the automated evidence was insufficient."


class FakeRetriever:
    """Small knowledge retriever with deterministic results (no embeddings)."""

    def __init__(self, results=None):
        self.results = results if results is not None else [
            {
                "id": "doc-1",
                "title": "technical_faq",
                "content": (
                    "Update the application to the latest version, clear the app "
                    "cache, restart the device, then try logging in again."
                ),
                "category": "technical",
                "similarity": 0.82,
            }
        ]

    def retrieve(self, query, top_k=4, category=None, threshold=0.0):
        return self.results[:top_k]

    @staticmethod
    def is_sufficient(results, min_similarity=0.25):
        return bool(results)

    @staticmethod
    def format_context(results):
        return "\n\n".join(
            f"[Source: {r['title']}]\n{r['content']}" for r in results
        )

    @staticmethod
    def source_titles(results):
        seen, titles = set(), []
        for item in results:
            if item.get("title") not in seen:
                seen.add(item.get("title"))
                titles.append(item.get("title"))
        return titles


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture
def fake_groq():
    return FakeGroq()


@pytest.fixture
def fake_retriever():
    return FakeRetriever()


@pytest.fixture
def demo_ticket(fake_repo):
    user = fake_repo.get_or_create_user("Test Student", "test.student@example.com")
    ticket = fake_repo.create_ticket(
        user["id"],
        "My payment was deducted twice",
        "I was charged twice for TXN1001. Please refund the duplicate.",
        priority="high",
    )
    fake_repo.add_payment(
        user["id"], "TXN1001", 49.99, "completed", "Pro subscription monthly"
    )
    fake_repo.add_payment(
        user["id"], "TXN1002", 49.99, "completed", "Pro subscription duplicate"
    )
    return {**ticket, "user": user}
