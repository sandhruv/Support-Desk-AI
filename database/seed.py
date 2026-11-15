"""Seed the Supabase database with demo users, tickets and mock payments.

Run with:  python run.py seed      (or: python -m database.seed)

IMPORTANT: This inserts DEMO data only. It is safe to run multiple times
(the script checks for existing records first).
"""

from __future__ import annotations

import logging

from database.connection import check_database_connection
from database.repository import Repository

logger = logging.getLogger(__name__)

DEMO_USER = {"name": "Aarav Sharma", "email": "aarav.sharma@example.com"}

DEMO_PAYMENTS = [
    {
        "transaction_ref": "TXN1001",
        "amount": 49.99,
        "status": "completed",
        "description": "Pro subscription - monthly",
    },
    {
        "transaction_ref": "TXN1002",
        "amount": 49.99,
        "status": "completed",
        "description": "Pro subscription - monthly (duplicate)",
    },
    {
        "transaction_ref": "TXN1003",
        "amount": 149.00,
        "status": "failed",
        "description": "Annual plan upgrade attempt",
    },
]

DEMO_TICKETS = [
    {
        "subject": "My payment was deducted twice",
        "message": (
            "I upgraded to the Pro plan yesterday and my card was deducted twice. "
            "Transaction reference TXN1001. Please refund the duplicate charge."
        ),
        "priority": "high",
    },
    {
        "subject": "Application crashes whenever I try to log in",
        "message": (
            "The app crashes every single time I try to log in. I already "
            "reinstalled it once. I am on Android 14."
        ),
        "priority": "medium",
    },
    {
        "subject": "Cannot access my account after password reset",
        "message": (
            "I forgot my password and requested a reset link, but I am not "
            "receiving the email. I need access to my account."
        ),
        "priority": "medium",
    },
]


def main() -> None:
    ok, message = check_database_connection()
    print(message)
    if not ok:
        print(
            "\nNothing was seeded. Configure DATABASE_URL in .env and run the "
            "SQL migrations first:\n"
            "  database/migrations/001_initial_schema.sql\n"
            "  database/migrations/002_vector_search.sql\n"
            "  database/migrations/003_security_policies.sql"
        )
        return

    repo = Repository()
    user = repo.get_or_create_user(DEMO_USER["name"], DEMO_USER["email"])
    print(f"Demo user: {user['email']} ({user['id']})")

    for payment in DEMO_PAYMENTS:
        repo.insert_payment_record(user_id=user["id"], **payment)
    print(f"Mock payment records ensured: {len(DEMO_PAYMENTS)}")

    existing = repo.list_tickets(search=DEMO_USER["email"], limit=50)
    existing_subjects = {t["subject"] for t in existing if t["user_id"] == user["id"]}
    created = 0
    for item in DEMO_TICKETS:
        if item["subject"] in existing_subjects:
            continue
        ticket = repo.create_ticket(
            user_id=user["id"],
            subject=item["subject"],
            message=item["message"],
            priority=item["priority"],
        )
        repo.add_conversation(
            ticket_id=ticket["id"],
            user_id=user["id"],
            role="customer",
            message=item["message"],
        )
        created += 1
    print(f"Demo tickets created: {created} (existing kept)")

    print("\nNext steps:")
    print("  1. python run.py ingest   -> embed knowledge_base documents into pgvector")
    print("  2. python run.py api      -> start FastAPI on :8000")
    print("  3. python run.py ui       -> start Streamlit dashboard")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
