"""Classifier Agent tools.

Two real Python tools:
1. keyword_classification_tool  - deterministic keyword scoring
2. classification_validation_tool - validates/normalises LLM output
Both are also exposed as Semantic Kernel plugin functions.
"""

from __future__ import annotations

import json
from typing import Optional

from semantic_kernel.functions import kernel_function

CATEGORY_KEYWORDS = {
    "billing": [
        "payment", "paid", "pay", "charge", "charged", "deducted", "deduct",
        "refund", "invoice", "billing", "subscription", "transaction", "txn",
        "double", "twice", "money", "amount", "card", "credit", "debit",
        "overcharged", "fee",
    ],
    "technical": [
        "crash", "crashes", "crashing", "error", "bug", "broken", "not working",
        "doesn't work", "does not work", "freeze", "freezes", "login", "loading",
        "slow", "performance", "exception", "500", "timeout", "app", "application",
        "install", "update", "glitch",
    ],
    "account": [
        "account", "password", "reset", "access", "locked", "sign in", "signin",
        "log in", "login", "email", "profile", "verify", "verification",
        "username", "2fa", "otp", "recovery", "disabled",
    ],
}

ALIASES = {
    "payments": "billing", "payment": "billing", "billing_issue": "billing",
    "tech": "technical", "technical_issue": "technical",
    "login": "account", "access": "account", "account_issue": "account",
    "general": "other", "other": "other",
    "billing": "billing", "technical": "technical", "account": "account",
}


def keyword_classification_tool(message: str, subject: str = "") -> dict:
    """Score the message against keyword dictionaries (deterministic tool)."""
    text = f"{subject} {message}".lower()
    scores = {category: 0 for category in CATEGORY_KEYWORDS}
    matched: dict[str, list[str]] = {category: [] for category in CATEGORY_KEYWORDS}

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                scores[category] += 1
                matched[category].append(keyword)

    total = sum(scores.values())
    if total == 0:
        return {
            "category": "other",
            "confidence": 0.30,
            "scores": scores,
            "matched_keywords": matched,
            "method": "keyword",
            "notes": "No category keywords matched.",
        }

    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]
    if best_score == 0:
        return {
            "category": "other", "confidence": 0.30, "scores": scores,
            "matched_keywords": matched, "method": "keyword",
            "notes": "No dominant category.",
        }

    dominance = best_score / total
    confidence = 0.55 + 0.40 * dominance
    if best_score == 1:
        confidence = min(confidence, 0.60)
    confidence = round(min(confidence, 0.95), 3)

    return {
        "category": best_category,
        "confidence": confidence,
        "scores": scores,
        "matched_keywords": matched,
        "method": "keyword",
        "notes": f"Matched {best_score} keyword(s) for '{best_category}'.",
    }


def classification_validation_tool(
    category: str,
    confidence: float,
    message: str = "",
    keyword_result: Optional[dict] = None,
) -> dict:
    """Validate and normalise a classification before routing.

    - normalises aliases and invalid categories to the keyword fallback
    - clamps confidence to [0, 1]
    - lowers confidence when the LLM and keyword tools disagree strongly
    - decides whether escalation is required (< 70% or 'other')
    """
    notes: list[str] = []
    normalized = ALIASES.get((category or "").strip().lower())
    if normalized is None:
        normalized = "other"
        notes.append("Unknown category normalised to 'other'.")

    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 0.0
        notes.append("Non-numeric confidence reset to 0.")
    conf = max(0.0, min(1.0, conf))

    if keyword_result is None and message:
        keyword_result = keyword_classification_tool(message)

    if keyword_result:
        kw_category = keyword_result.get("category")
        kw_scores = keyword_result.get("scores") or {}
        kw_top = max(kw_scores.values()) if kw_scores else 0
        if kw_category and kw_category != normalized and kw_top >= 2:
            conf = max(0.05, round(conf - 0.15, 3))
            notes.append(
                f"LLM category '{normalized}' disagreed with keywords "
                f"('{kw_category}'); confidence lowered."
            )
        if kw_category and kw_category != normalized and kw_top >= 3:
            normalized = kw_category
            notes.append(f"Category corrected to keyword result '{kw_category}'.")

    needs_escalation = conf < 0.70 or normalized == "other"
    return {
        "category": normalized,
        "confidence": round(conf, 3),
        "is_confident": not needs_escalation,
        "needs_escalation": needs_escalation,
        "notes": notes,
    }


class ClassificationTools:
    """Semantic Kernel plugin exposing the classifier tools."""

    plugin_name = "classification_tools"

    @kernel_function(name="keyword_classification_tool", description="Keyword-based ticket classification scoring.")
    def keyword_tool(self, message: str, subject: str = "") -> str:
        return json.dumps(keyword_classification_tool(message, subject))

    @kernel_function(name="classification_validation_tool", description="Validate and normalise a ticket classification.")
    def validation_tool(self, category: str, confidence: float, message: str = "") -> str:
        return json.dumps(classification_validation_tool(category, confidence, message))

    # Direct fallbacks for environments where the kernel invoke API differs
    direct = {
        "keyword_classification_tool": keyword_classification_tool,
        "classification_validation_tool": classification_validation_tool,
    }
