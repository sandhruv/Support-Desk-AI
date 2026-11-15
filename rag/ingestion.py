"""Knowledge base ingestion: load -> clean -> chunk -> embed -> store.

All chunks and their pgvector embeddings are stored in Supabase PostgreSQL.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

from database.repository import Repository
from rag.chunking import chunk_text
from rag.document_loader import load_directory, load_file
from rag.embeddings import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class KnowledgeIngestion:
    def __init__(
        self,
        repository: Repository,
        embedder: Optional[EmbeddingService] = None,
        chunk_size: int = 800,
        overlap: int = 120,
    ):
        self.repository = repository
        self.embedder = embedder or get_embedding_service()
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.last_status: dict = {"state": "idle", "documents": 0, "chunks": 0, "errors": []}

    # ------------------------------------------------------------------
    def ingest_documents(self, documents: Iterable[dict], replace: bool = True) -> dict:
        """Ingest in-memory documents: [{title, content, category}]."""
        docs = list(documents)
        stats = {"documents": 0, "chunks": 0, "errors": [], "titles": []}
        self.last_status = {"state": "running", **stats}

        for doc in docs:
            title = (doc.get("title") or "untitled").strip()
            content = (doc.get("content") or "").strip()
            category = doc.get("category")
            if not content:
                stats["errors"].append(f"{title}: empty content")
                continue
            try:
                chunks = chunk_text(content, self.chunk_size, self.overlap)
                if not chunks:
                    stats["errors"].append(f"{title}: no chunks produced")
                    continue
                if replace:
                    self.repository.delete_knowledge_by_title(title)
                embeddings = self.embedder.encode(chunks)
                if len(embeddings) != len(chunks):
                    raise ValueError("embedding count does not match chunk count")
                for index, (chunk, vector) in enumerate(zip(chunks, embeddings)):
                    self.repository.insert_knowledge_document(
                        title=title,
                        content=chunk,
                        category=category,
                        embedding=vector,
                        metadata={
                            "chunk_index": index,
                            "chunk_count": len(chunks),
                            "source": doc.get("source", title),
                        },
                    )
                stats["documents"] += 1
                stats["chunks"] += len(chunks)
                stats["titles"].append(title)
            except Exception as exc:
                logger.exception("Failed to ingest %s", title)
                stats["errors"].append(f"{title}: {exc}")

        stats["state"] = "completed" if not stats["errors"] else "completed_with_errors"
        self.last_status = stats
        return stats

    # ------------------------------------------------------------------
    def ingest_directory(
        self, directory: str | Path | None = None, replace: bool = True
    ) -> dict:
        directory = Path(directory) if directory else PROJECT_ROOT / "knowledge_base"
        documents = load_directory(directory)
        return self.ingest_documents(documents, replace=replace)

    def ingest_file(
        self,
        path: str | Path,
        title: Optional[str] = None,
        category: Optional[str] = None,
        replace: bool = True,
    ) -> dict:
        document = load_file(path, category=category)
        if title:
            document["title"] = title.strip()
        return self.ingest_documents([document], replace=replace)

    def get_status(self) -> dict:
        return dict(self.last_status)
