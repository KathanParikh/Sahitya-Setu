"""Hybrid retrieval: BM25 + vector search fused with Reciprocal Rank Fusion.

RRF scores a document by the sum of 1/(k + rank) over the ranked lists it
appears in. It needs no score normalisation — BM25 scores are unbounded and
cosine similarities live in [-1, 1], so averaging them directly would let one
list dominate the other for arbitrary reasons. Rank position is the only
signal RRF uses, which is exactly what makes it robust here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import config
from indexing import bm25_index, vector_store
from indexing.embedder import embed_query

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    page_start: int
    page_end: int
    chapter_index: int
    chapter_title: str
    rrf_score: float
    bm25_rank: Optional[int] = None
    vector_rank: Optional[int] = None
    bm25_score: Optional[float] = None
    vector_score: Optional[float] = None

    @property
    def sources(self) -> List[str]:
        s = []
        if self.bm25_rank is not None:
            s.append("bm25")
        if self.vector_rank is not None:
            s.append("vector")
        return s

    def citation(self) -> str:
        pages = (f"પાનું {self.page_start}" if self.page_start == self.page_end
                 else f"પાનાં {self.page_start}-{self.page_end}")
        return f"{pages} | {self.chapter_title}" if self.chapter_title else pages

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chapter_index": self.chapter_index,
            "chapter_title": self.chapter_title,
            "rrf_score": round(self.rrf_score, 6),
            "bm25_rank": self.bm25_rank,
            "vector_rank": self.vector_rank,
            "sources": self.sources,
        }


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[str]], k: int = None
) -> Dict[str, float]:
    """Fuse ranked id lists into {id: score}. Higher is better."""
    k = k if k is not None else config.RRF_K
    scores: Dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def hybrid_search(
    doc_id: str,
    query: str,
    top_k: int = None,
    bm25_k: int = None,
    vector_k: int = None,
) -> List[RetrievedChunk]:
    """Run both retrievers, fuse with RRF, return the top_k merged chunks."""
    top_k = top_k or config.FINAL_TOP_K
    bm25_k = bm25_k or config.BM25_TOP_K
    vector_k = vector_k or config.VECTOR_TOP_K

    # --- lexical half -------------------------------------------------------
    bm25_hits = []
    index = bm25_index.get_index(doc_id)
    if index is not None:
        bm25_hits = index.search(query, top_k=bm25_k)
    else:
        logger.warning("No BM25 index for %s; running vector-only.", doc_id)

    # --- semantic half ------------------------------------------------------
    try:
        vector_hits = vector_store.search(doc_id, embed_query(query), top_k=vector_k)
    except Exception as exc:
        logger.error("Vector search failed for %s: %s", doc_id, exc)
        vector_hits = []

    if not bm25_hits and not vector_hits:
        return []

    fused = reciprocal_rank_fusion([
        [h.chunk_id for h in bm25_hits],
        [h["chunk_id"] for h in vector_hits],
    ])

    bm25_by_id = {h.chunk_id: h for h in bm25_hits}
    vector_by_id = {h["chunk_id"]: h for h in vector_hits}

    top_ids = sorted(fused, key=lambda cid: fused[cid], reverse=True)[:top_k]

    # BM25-only hits carry no text, so hydrate whatever the vector list missed.
    missing = [cid for cid in top_ids if cid not in vector_by_id]
    hydrated = vector_store.get_by_ids(doc_id, missing) if missing else {}

    results: List[RetrievedChunk] = []
    for chunk_id in top_ids:
        row = vector_by_id.get(chunk_id) or hydrated.get(chunk_id)
        if row is None:
            logger.warning("Chunk %s ranked but not found in the store.", chunk_id)
            continue
        meta = row.get("metadata") or {}
        bm = bm25_by_id.get(chunk_id)
        vec = vector_by_id.get(chunk_id)
        results.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                text=row.get("text", ""),
                page_start=int(meta.get("page_start", 0)),
                page_end=int(meta.get("page_end", 0)),
                chapter_index=int(meta.get("chapter_index", -1)),
                chapter_title=meta.get("chapter_title", "") or "",
                rrf_score=fused[chunk_id],
                bm25_rank=bm.rank if bm else None,
                bm25_score=bm.score if bm else None,
                vector_rank=vec["rank"] if vec else None,
                vector_score=vec["score"] if vec else None,
            )
        )
    return results
