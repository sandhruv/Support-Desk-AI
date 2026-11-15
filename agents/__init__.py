"""Five independent AI agents of the support desk."""

from agents.account_agent import AccountAgent
from agents.base_agent import AgentResult, BaseAgent
from agents.billing_agent import BillingAgent
from agents.classifier_agent import ClassifierAgent
from agents.escalation_agent import EscalationAgent
from agents.technical_agent import TechnicalAgent

__all__ = [
    "AccountAgent",
    "AgentResult",
    "BaseAgent",
    "BillingAgent",
    "ClassifierAgent",
    "EscalationAgent",
    "TechnicalAgent",
]
