"""Persistent conversation memory stored in Supabase.

Every customer message and AI/human response is written to the
``conversations`` table and reloaded when needed, so follow-up questions
(e.g. "TXN1001" referring to a previously mentioned failed payment) work
across sessions and processes. No in-memory dictionaries are used for
permanent storage.
"""

from __future__ import annotations

from typing import Optional


class ConversationMemory:
    def __init__(self, repository):
        self.repository = repository

    # ------------------------------------------------------------------
    def add_message(
        self, ticket_id: str, role: str, message: str, user_id: Optional[str] = None
    ) -> dict:
        if role not in ("customer", "assistant", "system", "human_support"):
            raise ValueError(f"Invalid conversation role: {role}")
        return self.repository.add_conversation(
            ticket_id=ticket_id,
            user_id=user_id,
            role=role,
            message=message,
        )

    def add_customer_message(self, ticket_id: str, message: str, user_id: Optional[str] = None):
        return self.add_message(ticket_id, "customer", message, user_id)

    def add_assistant_message(self, ticket_id: str, message: str, user_id: Optional[str] = None):
        return self.add_message(ticket_id, "assistant", message, user_id)

    def add_human_message(self, ticket_id: str, message: str, user_id: Optional[str] = None):
        return self.add_message(ticket_id, "human_support", message, user_id)

    # ------------------------------------------------------------------
    def get_history(self, ticket_id: str) -> list[dict]:
        return self.repository.get_conversation(ticket_id)

    def format_history(self, history: list[dict], limit: int = 12) -> str:
        """Render recent history for LLM prompts."""
        if not history:
            return "No previous conversation."
        labels = {
            "customer": "Customer",
            "assistant": "AI Assistant",
            "system": "System",
            "human_support": "Human Support",
        }
        lines = []
        for item in history[-limit:]:
            role = labels.get(item.get("role"), item.get("role", "unknown"))
            lines.append(f"{role}: {item.get('message', '')}")
        return "\n".join(lines)

    def get_context(self, ticket_id: str, limit: int = 12) -> str:
        return self.format_history(self.get_history(ticket_id), limit=limit)

    def find_transaction_reference(self, ticket_id: str) -> Optional[str]:
        """Look back through the conversation for a TXN reference (follow-ups)."""
        import re

        for item in reversed(self.get_history(ticket_id)):
            match = re.search(r"\bTXN[0-9A-Z]+\b", item.get("message", ""), re.IGNORECASE)
            if match:
                return match.group(0).upper()
        return None
