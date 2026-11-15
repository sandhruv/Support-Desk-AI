"""Technical Specialist tools.

Two real Python tools:
1. search_knowledge_base()      -> pgvector similarity search (RAG)
2. validate_technical_solution() -> grounding/citation checks
"""

from __future__ import annotations

import json
import re

from semantic_kernel.functions import kernel_function

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "you", "your", "when", "whenever",
    "have", "has", "are", "was", "were", "will", "would", "can", "could", "should",
    "please", "help", "need", "want", "get", "got", "not", "but", "from", "into",
    "app", "application", "issue", "problem", "error",
}


def _words(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-zA-Z0-9]{3,}", (text or "").lower())
        if word not in STOPWORDS
    }


def search_knowledge_base(retriever, query: str, top_k: int = 4) -> dict:
    """Retrieve relevant chunks from Supabase pgvector."""
    results = retriever.retrieve(query=query, top_k=top_k)
    return {
        "query": query,
        "results": results,
        "count": len(results),
        "is_sufficient": retriever.is_sufficient(results),
        "sources": retriever.source_titles(results),
    }


def validate_technical_solution(solution: str, sources: str = "") -> dict:
    """Check that the generated answer is grounded in retrieved sources."""
    warnings: list[str] = []
    citations: list[str] = []

    try:
        parsed_sources = json.loads(sources) if isinstance(sources, str) else sources
    except json.JSONDecodeError:
        parsed_sources = []
    if isinstance(parsed_sources, dict):
        parsed_sources = parsed_sources.get("results", [])
    parsed_sources = parsed_sources or []

    if not solution or len(solution.strip()) < 40:
        warnings.append("Solution is too short to be useful.")
    if not parsed_sources:
        warnings.append("No retrieved sources were provided.")
        return {
            "valid": False,
            "grounded": False,
            "citations": [],
            "mentioned_sources": [],
            "warnings": warnings,
        }

    source_text = " ".join(
        (item.get("content") or "") for item in parsed_sources if isinstance(item, dict)
    )
    source_titles = [
        item.get("title") for item in parsed_sources
        if isinstance(item, dict) and item.get("title")
    ]
    citations = sorted(set(source_titles))

    overlap = len(_words(solution) & _words(source_text))
    grounded = overlap >= 3
    if not grounded:
        warnings.append("Answer has little lexical overlap with the retrieved sources.")

    mentioned = [
        title for title in citations if title and title.lower() in (solution or "").lower()
    ]
    if citations and not mentioned:
        warnings.append("Answer does not cite the retrieved source titles.")
        grounded = False

    return {
        "valid": grounded and len(solution or "") >= 40,
        "grounded": grounded,
        "citations": citations,
        "mentioned_sources": mentioned,
        "warnings": warnings,
    }


class TechnicalTools:
    """Semantic Kernel plugin exposing the technical tools."""

    plugin_name = "technical_tools"

    def __init__(self, retriever):
        self.retriever = retriever

    @kernel_function(name="search_knowledge_base", description="Semantic search over the Supabase pgvector knowledge base.")
    def search_tool(self, query: str, top_k: int = 4) -> str:
        return json.dumps(search_knowledge_base(self.retriever, query, top_k))

    @kernel_function(name="validate_technical_solution", description="Validate that a technical answer is grounded and cites sources.")
    def validate_tool(self, solution: str, sources: str = "") -> str:
        return json.dumps(validate_technical_solution(solution, sources))

    @property
    def direct(self) -> dict:
        return {
            "search_knowledge_base": lambda **kwargs: search_knowledge_base(
                self.retriever, **kwargs
            ),
            "validate_technical_solution": validate_technical_solution,
        }
