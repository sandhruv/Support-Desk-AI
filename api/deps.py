"""Dependency container for the FastAPI backend.

Services are created lazily so importing the app never requires database
credentials or network access. The Supabase service key stays server-side.
"""

from __future__ import annotations

from functools import lru_cache

from database.repository import Repository
from llm.groq_client import GroqClient
from memory.conversation_memory import ConversationMemory
from orchestration.coordinator import SupportCoordinator
from rag.ingestion import KnowledgeIngestion
from rag.retriever import KnowledgeRetriever


class Services:
    def __init__(self):
        self.repository = Repository()
        self.groq = GroqClient()
        self.memory = ConversationMemory(self.repository)
        self.retriever = KnowledgeRetriever(self.repository)
        self.ingestion = KnowledgeIngestion(self.repository)
        self.coordinator = SupportCoordinator(
            repository=self.repository,
            groq=self.groq,
            memory=self.memory,
            retriever=self.retriever,
        )


@lru_cache(maxsize=1)
def get_services() -> Services:
    return Services()


def reset_services() -> None:
    get_services.cache_clear()
