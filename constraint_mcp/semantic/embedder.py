"""Thin wrapper around fastembed for text embeddings.

Loads the model once per server process (lazy), caches embeddings by text, and
exposes cosine similarity. All embeddings are L2-normalized at embed time so the
dot product equals cosine similarity.
"""

from __future__ import annotations

import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "BAAI/bge-small-en-v1.5"


class EmbeddingEngine:
    """Wraps fastembed ``TextEmbedding``.

    Default model ``BAAI/bge-small-en-v1.5``: 384 dimensions, ~22MB CPU-only
    download (cached in ``~/.cache/fastembed/`` on first use), Apache 2.0.
    """

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or os.environ.get(
            "CONSTRAINT_MCP_SEMANTIC_MODEL", DEFAULT_MODEL_ID
        )
        self._model = None  # lazy load — avoid import cost when semantic layer is unused
        self._cache: dict[str, np.ndarray] = {}

    def _ensure_model(self) -> None:
        if self._model is None:
            from fastembed import TextEmbedding  # imported lazily

            logger.info("Loading embedding model %s (first call may download weights).", self.model_id)
            self._model = TextEmbedding(model_name=self.model_id)

    def embed(self, text: str) -> np.ndarray:
        """Return a normalized 1D float32 ndarray of shape (384,).

        Results are cached by text content for the lifetime of the process.
        """
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        self._ensure_model()
        vector = list(self._model.embed([text]))[0]
        vector = np.asarray(vector, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        self._cache[text] = vector
        return vector

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity. Both inputs must be normalized (use :meth:`embed`)."""
        return float(np.dot(a, b))


# Module-level singleton — imported by SemanticChecker.
embedding_engine = EmbeddingEngine()
