"""Semantic retrieval on top of Supabase pgvector.

Flow: query text -> local 384-dim embedding -> match_knowledge_chunks()
SQL function -> ranked document chunks with titles and similarities.
"""

from __future__ import annotations

from typing import Optional

from database.repository import Repository
from rag.embeddings import EmbeddingService, get_embedding_service


class KnowledgeRetriever:
    def __init__(
        self,
        repository: Repository,
        embedder: Optional[EmbeddingService] = None,
    ):
        self.repository = repository
        self.embedder = embedder or get_embedding_service()

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        category: Optional[str] = None,
        threshold: float = 0.0,
    ) -> list[dict]:
        """Return the most relevant knowledge chunks for a query."""
        if not query or not query.strip():
            return []
        embedding = self.embedder.encode_one(query)
        results = self.repository.similarity_search(
            embedding=embedding,
            top_k=top_k,
            category=category,
            threshold=threshold,
        )
        # Normalise for easy downstream use
        for item in results:
            item["similarity"] = round(float(item.get("similarity") or 0.0), 4)
        return results

    @staticmethod
    def is_sufficient(results: list[dict], min_similarity: float = 0.25) -> bool:
        """Decide whether retrieved context is good enough to answer safely."""
        return bool(results) and max(
            (float(r.get("similarity") or 0.0) for r in results), default=0.0
        ) >= min_similarity

    @staticmethod
    def format_context(results: list[dict]) -> str:
        """Format retrieved chunks for the LLM prompt, with source titles."""
        if not results:
            return "No relevant knowledge base passages were found."
        blocks = []
        for index, item in enumerate(results, start=1):
            blocks.append(
                f"[Passage {index}] [Source: {item.get('title', 'unknown')}] "
                f"(similarity {item.get('similarity', 0):.2f})\n"
                f"{item.get('content', '').strip()}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def source_titles(results: list[dict]) -> list[str]:
        seen, titles = set(), []
        for item in results:
            title = item.get("title")
            if title and title not in seen:
                seen.add(title)
                titles.append(title)
        return titles
