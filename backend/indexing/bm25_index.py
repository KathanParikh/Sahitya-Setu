"""BM25 keyword index — one pickled index per document.

This is the half of hybrid search that never misses an exact string. Gujarati
literature is dense with proper nouns (character names, village names, coined
literary terms) that a multilingual embedding model has likely never seen;
BM25 matches them on the surface form regardless.
"""
from __future__ import annotations

import logging
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import config

logger = logging.getLogger(__name__)

# Keep letters and digits of any script, drop punctuation. \w under re.UNICODE
# already covers the Gujarati block.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# High-frequency Gujarati function words carry no discriminative signal and
# inflate BM25 scores for long chunks.
GUJARATI_STOPWORDS = {
    "અને", "છે", "હતો", "હતી", "હતું", "હતા", "તે", "તેઓ", "આ", "એ", "માં",
    "થી", "ને", "નો", "ની", "નું", "ના", "પણ", "કે", "જે", "જેમ", "માટે",
    "સાથે", "પર", "કર્યું", "કરી", "કરે", "હોય", "શકે", "એક", "તો", "જ",
    "શું", "કેમ", "અહીં", "ત્યાં", "હવે", "પછી", "ખૂબ", "બહુ",
}


def tokenize(text: str, remove_stopwords: bool = True) -> List[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text or "")]
    if remove_stopwords:
        tokens = [t for t in tokens if t not in GUJARATI_STOPWORDS]
    return tokens


@dataclass
class BM25Result:
    chunk_id: str
    score: float
    rank: int  # 1-based, what RRF consumes


class BM25Index:
    """An in-memory BM25Okapi index plus the chunk ids it was built over."""

    def __init__(self, chunk_ids: Sequence[str], corpus_tokens: Sequence[Sequence[str]]):
        from rank_bm25 import BM25Okapi

        self.chunk_ids: List[str] = list(chunk_ids)
        self.corpus_tokens: List[List[str]] = [list(t) for t in corpus_tokens]
        self._bm25 = BM25Okapi(self.corpus_tokens)

    # ------------------------------------------------------------ build ----
    @classmethod
    def build(cls, chunks: Sequence) -> "BM25Index":
        """Build from Chunk objects (anything with .chunk_id and .text)."""
        ids = [c.chunk_id for c in chunks]
        tokens = [tokenize(c.text) for c in chunks]
        # rank_bm25 divides by the average document length; an all-empty corpus
        # would make that zero.
        tokens = [t if t else ["\u0000"] for t in tokens]
        return cls(ids, tokens)

    # ----------------------------------------------------------- search ----
    def search(self, query: str, top_k: int = None) -> List[BM25Result]:
        top_k = top_k or config.BM25_TOP_K
        query_tokens = tokenize(query)
        if not query_tokens:
            # An all-stopword query still deserves an attempt.
            query_tokens = tokenize(query, remove_stopwords=False)
        if not query_tokens or not self.chunk_ids:
            return []

        scores = self._bm25.get_scores(query_tokens)
        ordered = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results: List[BM25Result] = []
        for rank, i in enumerate(ordered[:top_k], start=1):
            if scores[i] <= 0:
                break  # no term overlap at all past this point
            results.append(BM25Result(self.chunk_ids[i], float(scores[i]), rank))
        return results

    # ------------------------------------------------------ persistence ----
    def save(self, path: str | Path) -> Path:
        """Pickle the corpus, not the BM25Okapi object.

        Re-fitting on load costs milliseconds and avoids pickles that break
        whenever rank_bm25 changes its internals.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(
                {"version": 1, "chunk_ids": self.chunk_ids, "corpus_tokens": self.corpus_tokens},
                fh,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        return path

    @classmethod
    def load(cls, path: str | Path) -> "BM25Index":
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
        return cls(payload["chunk_ids"], payload["corpus_tokens"])


def index_path_for(doc_id: str) -> Path:
    return config.BM25_DIR / f"{doc_id}.pkl"


# A small process-level cache so repeated questions against the same book do
# not re-read and re-fit the index on every request.
_cache: Dict[str, BM25Index] = {}


def get_index(doc_id: str) -> Optional[BM25Index]:
    if doc_id in _cache:
        return _cache[doc_id]
    path = index_path_for(doc_id)
    if not path.exists():
        return None
    try:
        _cache[doc_id] = BM25Index.load(path)
        return _cache[doc_id]
    except Exception as exc:
        logger.error("Could not load BM25 index for %s: %s", doc_id, exc)
        return None


def build_and_save(doc_id: str, chunks: Sequence) -> Path:
    index = BM25Index.build(chunks)
    path = index.save(index_path_for(doc_id))
    _cache[doc_id] = index
    return path


def delete_index(doc_id: str) -> None:
    _cache.pop(doc_id, None)
    path = index_path_for(doc_id)
    if path.exists():
        path.unlink()
