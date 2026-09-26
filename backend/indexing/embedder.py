"""multilingual-e5-base embeddings, loaded once and run on CPU.

e5 is an asymmetric model: passages and queries must be prefixed differently
("passage: " / "query: "). Getting this wrong silently degrades recall, so the
prefixes are applied here rather than left to callers.
"""
from __future__ import annotations

import logging
import threading
from typing import Iterable, List, Optional, Sequence

import config

logger = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def get_model():
    """Load the SentenceTransformer once per process (thread-safe)."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model %s (CPU)...", config.EMBEDDING_MODEL)
                _model = SentenceTransformer(config.EMBEDDING_MODEL, device="cpu")
                logger.info("Embedding model ready.")
    return _model


def _encode(texts: Sequence[str], prefix: str, show_progress: bool = False) -> List[List[float]]:
    if not texts:
        return []
    model = get_model()
    prefixed = [prefix + t for t in texts]
    vectors = model.encode(
        prefixed,
        batch_size=config.EMBEDDING_BATCH_SIZE,
        # Cosine similarity on unit vectors is just a dot product, which is
        # what Chroma's default index computes.
        normalize_embeddings=True,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
    )
    return [v.tolist() for v in vectors]


def embed_passages(texts: Sequence[str], show_progress: bool = False) -> List[List[float]]:
    """Embed document chunks for indexing."""
    return _encode(texts, config.E5_PASSAGE_PREFIX, show_progress)


def embed_query(text: str) -> List[float]:
    """Embed a single user question for retrieval."""
    return _encode([text], config.E5_QUERY_PREFIX)[0]


def embed_queries(texts: Sequence[str]) -> List[List[float]]:
    return _encode(texts, config.E5_QUERY_PREFIX)


def warm_up() -> None:
    """Pull the model into memory at server start instead of on first request."""
    try:
        embed_query("ઉષ્ણતામાન")
    except Exception as exc:
        logger.warning("Embedding warm-up failed: %s", exc)
