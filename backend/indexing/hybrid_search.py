"""Hybrid retrieval: BM25 + vector search fused with Reciprocal Rank Fusion.

RRF scores a document by the sum of 1/(k + rank) over the ranked lists it
appears in. It needs no score normalisation — BM25 scores are unbounded and
cosine similarities live in [-1, 1], so averaging them directly would let one
list dominate the other for arbitrary reasons. Rank position is the only
signal RRF uses, which is exactly what makes it robust here.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import config
from indexing import bm25_index, vector_store
from indexing.embedder import embed_query

logger = logging.getLogger(__name__)

# Gujarati Unicode block. Same range as qa.prompt_builder uses to detect the
# question language; kept separate so indexing does not import from qa.
_GUJARATI = re.compile(r"[઀-૿]")


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
    extra_vector_query: Optional[str] = None,
) -> List[RetrievedChunk]:
    """Run both retrievers, fuse with RRF, return the top_k merged chunks.

    `extra_vector_query` adds a third ranked list: a vector search for a second
    wording of the same question. For an English question, `query` is its
    Gujarati translation and this is the original English, so a bad
    translation still leaves the English search in the fusion.
    """
    top_k = top_k or config.FINAL_TOP_K
    bm25_k = bm25_k or config.BM25_TOP_K
    vector_k = vector_k or config.VECTOR_TOP_K

    # --- lexical half -------------------------------------------------------
    # BM25 only matches exact words, so a query with no Gujarati script cannot
    # match the book's text ("born" never matches "જન્મ"). It still returned
    # hits on GujaratiBook.pdf, but only through stray English words like "in"
    # and "of" in a few chunks, and RRF ranked that noise alongside the vector
    # results, pushing the right passage out of the top 5. On 10 test questions
    # asked in English, skipping BM25 raised the right page in the top 5 from
    # 6/10 to 8/10. A Gujarati question with an English name mixed in still
    # contains Gujarati script, so it keeps BM25.
    bm25_hits = []
    if not _GUJARATI.search(query or ""):
        logger.info("Query has no Gujarati script; skipping BM25: %r", query)
    else:
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

    extra_hits = []
    if extra_vector_query:
        try:
            extra_hits = vector_store.search(doc_id, embed_query(extra_vector_query),
                                             top_k=vector_k)
        except Exception as exc:
            logger.error("Extra vector search failed for %s: %s", doc_id, exc)

    if not bm25_hits and not vector_hits and not extra_hits:
        return []

    fused = reciprocal_rank_fusion([
        [h.chunk_id for h in bm25_hits],
        [h["chunk_id"] for h in vector_hits],
        [h["chunk_id"] for h in extra_hits],
    ])

    bm25_by_id = {h.chunk_id: h for h in bm25_hits}
    # A chunk found by both vector searches keeps its rank from the main query.
    vector_by_id = {h["chunk_id"]: h for h in extra_hits}
    vector_by_id.update({h["chunk_id"]: h for h in vector_hits})

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


# ------------------------------------------------------------ widening -----
def _join_overlapping(a: str, b: str) -> str:
    """Join two consecutive chunks, dropping the sentences they share.

    The chunker starts each chunk with the last ~50 tokens of the previous one
    (processing.chunker._pack), so b usually begins with a's tail.
    """
    # Find where b's opening appears in a, then check that everything from
    # there to the end of a is how b begins. The earliest such point is the
    # longest overlap. 8 characters keeps a one-letter coincidence from
    # counting as an overlap.
    head = b[:8]
    at = a.find(head) if len(head) == 8 else -1
    while at != -1:
        if b.startswith(a[at:]):
            return a[:at] + b
        at = a.find(head, at + 1)
    return f"{a} {b}"


def widen_passages(doc_id: str, chunks: Sequence[RetrievedChunk],
                   top_n: int = None) -> List[RetrievedChunk]:
    """The top_n passages, each joined with the chunk before and after it.

    A scene can be cut by a chunk boundary: in 'ચીલઝડપ' the accusation of the
    thief ends chunk 152 (pages 93-94) and the proof, the wallet under the
    chair, opens chunk 153. The grader judges each passage on its own, so
    neither half was enough. Neighbours from another chapter are left out.
    Overlapping windows merge into one passage, ordered by their best rank.
    """
    top_n = top_n or config.WIDEN_TOP_N
    top = list(chunks[:top_n])
    centres = {}
    for rank, c in enumerate(top):
        try:
            centres[int(c.chunk_id.rsplit(":", 1)[1])] = (rank, c)
        except (IndexError, ValueError):
            continue  # not a plain '<doc>:<index>' id; leave it as it is
    if not centres:
        return top

    wanted = sorted({i + d for i in centres for d in (-1, 0, 1) if i + d >= 0})
    rows = vector_store.get_by_indexes(doc_id, wanted)

    # Keep neighbours in the same chapter as the passage they widen.
    keep = set(centres)
    for i, (_, c) in centres.items():
        for j in (i - 1, i + 1):
            row = rows.get(j)
            if row and int(row["metadata"].get("chapter_index", -1)) == c.chapter_index:
                keep.add(j)

    # Consecutive indexes form one passage.
    runs: List[List[int]] = []
    for i in sorted(keep):
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])

    widened = []
    for run in runs:
        best_rank, best = min(centres[i] for i in run if i in centres)
        texts = [rows[i]["text"] if i in rows else centres[i][1].text for i in run]
        text = texts[0]
        for nxt in texts[1:]:
            text = _join_overlapping(text, nxt)
        pages = [int(rows[i]["metadata"]["page_start"]) for i in run if i in rows] + \
                [int(rows[i]["metadata"]["page_end"]) for i in run if i in rows]
        widened.append((best_rank, RetrievedChunk(
            chunk_id=f"{doc_id}:{run[0]}-{run[-1]}" if len(run) > 1 else best.chunk_id,
            text=text,
            page_start=min(pages + [best.page_start]),
            page_end=max(pages + [best.page_end]),
            chapter_index=best.chapter_index,
            chapter_title=best.chapter_title,
            rrf_score=best.rrf_score,
            bm25_rank=best.bm25_rank,
            vector_rank=best.vector_rank,
            bm25_score=best.bm25_score,
            vector_score=best.vector_score,
        )))
    return [c for _, c in sorted(widened, key=lambda x: x[0])]
