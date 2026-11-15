"""Local embedding generation with sentence-transformers.

Model: sentence-transformers/all-MiniLM-L6-v2  ->  384 dimensions.
The model is loaded lazily (first use) so importing the project stays fast.
No external embedding API is used.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from llm.model_config import get_settings

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 384
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingService:
    """Thread-safe, lazily loaded sentence-transformers encoder."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or get_settings().embedding_model or DEFAULT_MODEL
        self._model = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info("Loading embedding model: %s", self.model_name)
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode a list of texts into 384-dimensional float vectors."""
        if not texts:
            return []
        cleaned = [t.strip() if t else "" for t in texts]
        model = self._load()
        vectors = model.encode(
            cleaned,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [list(map(float, vector)) for vector in vectors]

    def encode_one(self, text: str) -> list[float]:
        vectors = self.encode([text])
        if not vectors:
            raise ValueError("Cannot embed empty text")
        return vectors[0]


_shared_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Process-wide shared embedder (avoids reloading the model repeatedly)."""
    global _shared_service
    if _shared_service is None:
        _shared_service = EmbeddingService()
    return _shared_service
