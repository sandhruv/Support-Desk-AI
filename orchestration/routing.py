"""Routing logic for the router-to-specialists architecture."""

from __future__ import annotations

import json

from semantic_kernel.functions import kernel_function

from llm.model_config import (
    AGENT_ACCOUNT,
    AGENT_BILLING,
    AGENT_ESCALATION,
    AGENT_TECHNICAL,
    CONFIDENCE_THRESHOLD,
)

CATEGORY_TO_AGENT = {
    "billing": AGENT_BILLING,
    "technical": AGENT_TECHNICAL,
    "account": AGENT_ACCOUNT,
    "other": AGENT_ESCALATION,
}


def route_ticket(category: str, confidence: float, threshold: float = CONFIDENCE_THRESHOLD) -> dict:
    """Decide the next agent for a classified ticket.

    Low confidence or 'other' always routes to the Escalation Router.
    """
    category = (category or "other").lower()
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    if category not in CATEGORY_TO_AGENT:
        category = "other"

    if confidence < threshold:
        return {
            "next_agent": AGENT_ESCALATION,
            "escalate": True,
            "reason": f"Classification confidence {confidence:.0%} is below the "
                      f"{threshold:.0%} threshold.",
            "category": category,
        }
    if category == "other":
        return {
            "next_agent": AGENT_ESCALATION,
            "escalate": True,
            "reason": "Ticket could not be mapped to a supported specialist category.",
            "category": category,
        }
    return {
        "next_agent": CATEGORY_TO_AGENT[category],
        "escalate": False,
        "reason": f"Routed by category '{category}' with {confidence:.0%} confidence.",
        "category": category,
    }


class RoutingTools:
    """Semantic Kernel plugin for routing decisions."""

    plugin_name = "routing_tools"

    @kernel_function(name="route_ticket", description="Route a ticket to a specialist or escalation.")
    def route(self, category: str, confidence: float) -> str:
        return json.dumps(route_ticket(category, confidence))
