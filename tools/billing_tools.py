"""Billing Specialist tools.

Two real Python tools:
1. check_billing_policy()
2. lookup_payment_record()  -> queries mock payment_records in Supabase

IMPORTANT: no real financial transactions are processed. The agent never
claims a refund has been completed unless a payment system confirms it -
here no payment system exists, so the policy wording is always conditional.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from semantic_kernel.functions import kernel_function

POLICIES = {
    "duplicate_charge": (
        "Duplicate charge policy: if a customer is charged twice for the same "
        "transaction, the case is reviewed within 5-7 business days. A refund is "
        "issued to the original payment method only after review. Support agents "
        "must never confirm an instant refund; they may confirm that the duplicate "
        "charge is being investigated and provide the transaction reference."
    ),
    "refund": (
        "Refund policy: approved refunds are returned to the original payment "
        "method within 5-7 business days. Requests must include the transaction "
        "reference (e.g. TXN1001). Pending or failed transactions are not "
        "eligible for a refund until they settle."
    ),
    "invoice": (
        "Invoice policy: invoices are generated at the start of each billing "
        "cycle and can be re-sent to the registered email address. Billing "
        "details can be updated from the account settings page."
    ),
    "failed_payment": (
        "Failed payment policy: a failed transaction usually means the bank "
        "declined the charge. The customer should verify their card details and "
        "retry; no money is deducted for declined transactions."
    ),
    "general": (
        "General billing guidance: collect the transaction reference, verify the "
        "payment record, explain the applicable policy, and escalate cases that "
        "require a financial adjustment beyond standard policy."
    ),
}

TOPIC_KEYWORDS = {
    "duplicate_charge": ["twice", "double", "duplicate", "two times", "charged two"],
    "refund": ["refund", "money back", "return my money"],
    "invoice": ["invoice", "receipt", "bill"],
    "failed_payment": ["failed", "declined", "did not go through", "unsuccessful"],
}


def extract_transaction_reference(message: str) -> Optional[str]:
    """Find a TXN reference such as TXN1001 (tolerant of spacing and typos)."""
    text = message or ""
    match = re.search(r"\bTXN\s*[-_]?\s*([0-9A-Z]{3,})\b", text, re.IGNORECASE)
    if match:
        return f"TXN{match.group(1).upper()}"
    fuzzy = re.search(r"\b[tT][xXwW][xXnNmM]\s*[-_]?\s*(\d{3,})\b", text)
    if fuzzy:
        return f"TXN{fuzzy.group(1)}"
    return None


def check_billing_policy(topic: str = "") -> dict:
    """Return the applicable billing policy snippet (deterministic tool)."""
    text = (topic or "").lower()
    selected = "general"
    for topic_key, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            selected = topic_key
            break
    return {
        "topic": selected,
        "policy": POLICIES[selected],
        "available_topics": sorted(POLICIES),
    }


def lookup_payment_record(
    repository, user_id: str = "", transaction_ref: str = ""
) -> dict:
    """Query mock payment records from Supabase (deterministic tool)."""
    ref = (transaction_ref or "").strip().upper() or None
    records = repository.lookup_payment_records(
        user_id=user_id or None, transaction_ref=ref
    )
    return {
        "found": bool(records),
        "transaction_ref": ref,
        "records": records,
        "count": len(records),
        "note": (
            "Mock billing data stored in Supabase. No real transactions are processed."
        ),
    }


class BillingTools:
    """Semantic Kernel plugin exposing the billing tools."""

    plugin_name = "billing_tools"

    def __init__(self, repository):
        self.repository = repository

    @kernel_function(name="check_billing_policy", description="Look up the billing policy for a topic.")
    def policy_tool(self, topic: str = "") -> str:
        return json.dumps(check_billing_policy(topic))

    @kernel_function(name="lookup_payment_record", description="Look up mock payment records for a user or transaction reference.")
    def payment_tool(self, user_id: str = "", transaction_ref: str = "") -> str:
        return json.dumps(
            lookup_payment_record(self.repository, user_id=user_id, transaction_ref=transaction_ref)
        )

    @property
    def direct(self) -> dict:
        return {
            "check_billing_policy": check_billing_policy,
            "lookup_payment_record": lambda **kwargs: lookup_payment_record(
                self.repository, **kwargs
            ),
        }
