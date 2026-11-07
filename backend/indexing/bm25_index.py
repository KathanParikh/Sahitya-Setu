"""BM25 keyword index — built in memory from a book's chunks.

This is the half of hybrid search that never misses an exact string. Gujarati
literature is dense with proper nouns (character names, village names, coined
literary terms) that a multilingual embedding model has likely never seen;
BM25 matches them on the surface form regardless. Tokens are not stored:
tokenizing a whole book takes milliseconds, and recomputing them means a
tokenizer change can never leave a stale index behind.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import config

logger = logging.getLogger(__name__)

# Zero-width (non-)joiners steer glyph shaping only; inside a word they would
# split it in two.
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200c\u200d"))

# High-frequency Gujarati function words carry no discriminative signal and
# inflate BM25 scores for long chunks.
GUJARATI_STOPWORDS = {
    "અને", "છે", "હતો", "હતી", "હતું", "હતા", "તે", "તેઓ", "આ", "એ", "માં",
    "થી", "ને", "નો", "ની", "નું", "ના", "પણ", "કે", "જે", "જેમ", "માટે",
    "સાથે", "પર", "કર્યું", "કરી", "કરે", "હોય", "શકે", "એક", "તો", "જ",
    "શું", "કેમ", "અહીં", "ત્યાં", "હવે", "પછી", "ખૂબ", "બહુ",
}


def _is_word_char(ch: str) -> bool:
    # Gujarati vowel signs, anusvara and virama are combining marks (Mn/Mc),
    # which \w does not match: a \w+ tokenizer cuts "નાટકમાં" into "ન" and
    # "ટકમ". Marks belong to the word they sit on.
    return ch.isalnum() or unicodedata.category(ch)[0] == "M"


def tokenize(text: str, remove_stopwords: bool = True) -> List[str]:
    text = unicodedata.normalize("NFC", (text or "").translate(_ZERO_WIDTH))
    words = "".join(ch if _is_word_char(ch) else " " for ch in text).split()
    tokens = [t.lower() for t in words]
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
    def build(cls, chunk_ids: Sequence[str], texts: Sequence[str]) -> "BM25Index":
        tokens = [tokenize(text) for text in texts]
        # rank_bm25 divides by the average document length; an all-empty corpus
        # would make that zero.
        tokens = [t if t else ["\u0000"] for t in tokens]
        return cls(chunk_ids, tokens)

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


# Fitting costs milliseconds, but reading a book's chunks is a database call, so
# the index is cached per book.
_cache: Dict[str, BM25Index] = {}


def get_index(doc_id: str) -> Optional[BM25Index]:
    if doc_id in _cache:
        return _cache[doc_id]
    from indexing import vector_store

    try:
        rows = vector_store.get_all_chunks(doc_id)
    except Exception as exc:
        logger.error("Could not read chunks for the BM25 index of %s: %s", doc_id, exc)
        return None
    if not rows:
        return None
    _cache[doc_id] = BM25Index.build([r["chunk_id"] for r in rows], [r["text"] for r in rows])
    return _cache[doc_id]


def delete_index(doc_id: str) -> None:
    _cache.pop(doc_id, None)
