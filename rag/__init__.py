"""RAG package: loading, chunking, embeddings, retrieval and ingestion."""

from rag.chunking import chunk_text
from rag.document_loader import load_directory, load_file
from rag.embeddings import EmbeddingService, get_embedding_service
from rag.ingestion import KnowledgeIngestion
from rag.retriever import KnowledgeRetriever

__all__ = [
    "chunk_text",
    "load_directory",
    "load_file",
    "EmbeddingService",
    "get_embedding_service",
    "KnowledgeIngestion",
    "KnowledgeRetriever",
]
