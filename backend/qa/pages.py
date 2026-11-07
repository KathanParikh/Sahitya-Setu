"""Page-level source text, for exact page citations.

A chunk records only its first and last page. When it spans two pages, that
range does not say which page a given sentence is on, so it cannot prove a
citation. The page text can: ingestion stores every page exactly as it was
indexed (after OCR and running-header removal), so it matches what the chunks
were cut from, and answering a question never needs the PDF or OCR.

`page_text_source` is the single lookup used by the grounding check and the
answer prompt; tests replace it with fixtures.
"""
from __future__ import annotations

import functools
import logging
import re
from typing import Callable, Dict, Optional

from db import database

logger = logging.getLogger(__name__)

# Marks where a new page begins inside a passage shown to the model, so it can
# cite the exact page. Brackets no answer would naturally contain.
MARKER = "⟪પાનું {page}⟫"
# How much of a page's opening text must be found in the chunk to place a
# marker; shorter openings are too ambiguous to locate.
_MARKER_PREFIX_CHARS = 24


def save_book_pages(doc_id: str, pages) -> None:
    """Store the indexed text of every page (processing.pdf_extractor.Page)."""
    database.save_pages(doc_id, pages)
    _book_pages.cache_clear()


def delete_book_pages(doc_id: str) -> None:
    database.delete_pages(doc_id)
    _book_pages.cache_clear()


@functools.lru_cache(maxsize=4)
def _book_pages(doc_id: str) -> Dict[int, str]:
    return database.get_pages(doc_id)


def stored_page_text(doc_id: str, page: int) -> Optional[str]:
    """Text of one page of the uploaded book, or None if it cannot be read."""
    try:
        return _book_pages(doc_id).get(page) or None
    except Exception as exc:  # database unreachable
        logger.warning("Page text unavailable for %s: %s", doc_id, exc)
        return None


page_text_source: Callable[[str, int], Optional[str]] = stored_page_text


def page_text(doc_id: str, page: int) -> Optional[str]:
    return page_text_source(doc_id, page)


def doc_id_of(chunk) -> str:
    """Chunk ids are '<doc_id>:<index>'."""
    return chunk.chunk_id.rsplit(":", 1)[0]


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def with_page_markers(chunk) -> str:
    """The chunk's text with a marker where each later page begins.

    A marker is placed only where that page's opening words are found in the
    chunk; otherwise the passage is shown unmarked (the grounding check will
    still demand, and verify, an exact page).
    """
    text = _squash(chunk.text)
    if chunk.page_end <= chunk.page_start:
        return text
    doc_id = doc_id_of(chunk)
    for page in range(chunk.page_end, chunk.page_start, -1):  # right to left keeps offsets valid
        opening = _squash(page_text(doc_id, page) or "")[:_MARKER_PREFIX_CHARS]
        if len(opening) < _MARKER_PREFIX_CHARS:
            continue
        at = text.find(opening)
        if at > 0:
            text = f"{text[:at]}{MARKER.format(page=page)} {text[at:]}"
    return text
