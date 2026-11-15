"""Account Specialist tools.

Two real Python tools:
1. lookup_customer_account()      -> reads users + ticket summary from Supabase
2. validate_account_support_request() -> safety checks (never handle passwords)

Plaintext passwords are never stored, requested, or accepted.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from semantic_kernel.functions import kernel_function

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PASSWORD_PATTERN = re.compile(
    r"(?:my\s+password\s*(?:is|:)\s*)(\S+)|(?:password\s*[:=]\s*)(\S+)",
    re.IGNORECASE,
)


def lookup_customer_account(
    repository, user_id: str = "", email: str = ""
) -> dict:
    """Look up the customer account record and recent tickets (deterministic)."""
    user = None
    if user_id:
        user = repository.get_user(user_id)
    if user is None and email:
        user = repository.get_user_by_email(email)
    if user is None:
        return {"found": False, "user": None, "tickets": [], "ticket_count": 0}

    tickets = repository.list_tickets(search=user.get("email", ""), limit=20)
    own_tickets = [t for t in tickets if t.get("user_id") == user.get("id")]
    return {
        "found": True,
        "user": user,
        "tickets": own_tickets[:10],
        "ticket_count": len(own_tickets),
    }


def validate_account_support_request(message: str) -> dict:
    """Flag unsafe content (passwords) and redact it before logging."""
    message = message or ""
    violations: list[str] = []
    redacted = message

    if PASSWORD_PATTERN.search(message):
        violations.append("Customer message contains a password-like secret.")
        redacted = PASSWORD_PATTERN.sub("password: [REDACTED]", message)

    lowered = message.lower()
    if "send me your password" in lowered or "share your password" in lowered:
        violations.append("Request for password sharing detected.")

    if "password" not in lowered and "reset" not in lowered and "login" not in lowered:
        violations.append("Message does not describe an account access problem.")

    return {
        "safe_to_proceed": "Customer message contains a password-like secret." not in violations,
        "violations": violations,
        "redacted_message": redacted,
        "guidance": (
            "Never request or store passwords. Provide self-service reset steps "
            "and escalate if identity verification is required."
        ),
    }


def extract_email(message: str) -> Optional[str]:
    match = EMAIL_PATTERN.search(message or "")
    return match.group(0) if match else None


class AccountTools:
    """Semantic Kernel plugin exposing the account tools."""

    plugin_name = "account_tools"

    def __init__(self, repository):
        self.repository = repository

    @kernel_function(name="lookup_customer_account", description="Look up a customer account and recent tickets.")
    def lookup_tool(self, user_id: str = "", email: str = "") -> str:
        return json.dumps(
            lookup_customer_account(self.repository, user_id=user_id, email=email)
        )

    @kernel_function(name="validate_account_support_request", description="Check an account support message for unsafe password content.")
    def validate_tool(self, message: str) -> str:
        return json.dumps(validate_account_support_request(message))

    @property
    def direct(self) -> dict:
        return {
            "lookup_customer_account": lambda **kwargs: lookup_customer_account(
                self.repository, **kwargs
            ),
            "validate_account_support_request": validate_account_support_request,
        }
