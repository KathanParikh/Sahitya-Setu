"""ChromaDB persistence — one collection per uploaded book.

Per-document collections keep retrieval naturally scoped (a question about
book A can never surface a chunk from book B) and make deletion a single call.
Chroma also stores the chunk text, so it doubles as the lookup table that
hybrid search uses to turn BM25's chunk ids back into passages.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

import config

logger = logging.getLogger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        import chromadb
        from chromadb.config import Settings

        _client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False, allow_reset=False),
        )
    return _client


def collection_name(doc_id: str) -> str:
    # Chroma requires 3-63 chars, alphanumeric plus _ and -.
    return f"doc_{doc_id}"[:63]


def get_collection(doc_id: str, create: bool = False):
    client = get_client()
    name = collection_name(doc_id)
    if create:
        return client.get_or_create_collection(
            name=name,
            # Embeddings are supplied explicitly; cosine matches the
            # normalised vectors that embedder.py produces.
            metadata={"hnsw:space": "cosine", "doc_id": doc_id},
        )
    try:
        return client.get_collection(name=name)
    except Exception:
        return None


def add_chunks(doc_id: str, chunks: Sequence, embeddings: Sequence[Sequence[float]]) -> int:
    """Insert chunks and their vectors. Chunks and embeddings must align."""
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings length mismatch")
    if not chunks:
        return 0

    collection = get_collection(doc_id, create=True)
    # Chroma caps how much it will accept in one call; 500 is comfortably under
    # every backend's limit and keeps memory flat for a long book.
    batch = 500
    for start in range(0, len(chunks), batch):
        window = chunks[start:start + batch]
        collection.add(
            ids=[c.chunk_id for c in window],
            documents=[c.text for c in window],
            metadatas=[c.metadata() for c in window],
            embeddings=[list(e) for e in embeddings[start:start + batch]],
        )
    return len(chunks)


def _rows_from_get(result: dict) -> List[dict]:
    out: List[dict] = []
    ids = result.get("ids") or []
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    for i, chunk_id in enumerate(ids):
        out.append({
            "chunk_id": chunk_id,
            "text": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
        })
    return out


def search(doc_id: str, query_embedding: Sequence[float], top_k: int = None) -> List[dict]:
    """Vector search. Returns rows with chunk_id, text, metadata, score, rank."""
    top_k = top_k or config.VECTOR_TOP_K
    collection = get_collection(doc_id)
    if collection is None:
        return []

    result = collection.query(
        query_embeddings=[list(query_embedding)],
        n_results=min(top_k, max(collection.count(), 1)),
        include=["documents", "metadatas", "distances"],
    )
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    rows: List[dict] = []
    for rank, chunk_id in enumerate(ids, start=1):
        distance = dists[rank - 1] if rank - 1 < len(dists) else None
        rows.append({
            "chunk_id": chunk_id,
            "text": docs[rank - 1] if rank - 1 < len(docs) else "",
            "metadata": metas[rank - 1] if rank - 1 < len(metas) else {},
            # Cosine distance -> similarity, purely for display.
            "score": None if distance is None else 1.0 - float(distance),
            "rank": rank,
        })
    return rows


def get_by_ids(doc_id: str, chunk_ids: Sequence[str]) -> Dict[str, dict]:
    """Fetch chunks by id — how BM25 hits are hydrated into full passages."""
    if not chunk_ids:
        return {}
    collection = get_collection(doc_id)
    if collection is None:
        return {}
    result = collection.get(ids=list(chunk_ids), include=["documents", "metadatas"])
    return {row["chunk_id"]: row for row in _rows_from_get(result)}


def get_all_chunks(doc_id: str) -> List[dict]:
    """Every chunk in reading order — the input to summarisation."""
    collection = get_collection(doc_id)
    if collection is None:
        return []
    rows = _rows_from_get(collection.get(include=["documents", "metadatas"]))
    rows.sort(key=lambda r: r["metadata"].get("chunk_index", 0))
    return rows


def count(doc_id: str) -> int:
    collection = get_collection(doc_id)
    return collection.count() if collection is not None else 0


def delete_document(doc_id: str) -> None:
    try:
        get_client().delete_collection(collection_name(doc_id))
    except Exception as exc:
        logger.info("No vector collection to delete for %s (%s)", doc_id, exc)
