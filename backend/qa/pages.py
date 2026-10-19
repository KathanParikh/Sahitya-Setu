"""Page-level source text, for exact page citations.

A chunk records only its first and last page. When it spans two pages, that
range does not say which page a given sentence is on, so it cannot prove a
citation. The page text can: ingestion stores every page exactly as it was
indexed (after OCR and running-header removal), so it matches what the chunks
were cut from. Books indexed before that store existed fall back to rebuilding
the text from the uploaded PDF, OCR-ing scanned pages on demand.

`page_text_source` is the single lookup used by the grounding check and the
answer prompt; tests replace it with fixtures.
"""
from __future__ import annotations

import functools
import json
import logging
import re
from typing import Callable, Dict, Optional

import config

logger = logging.getLogger(__name__)

# Marks where a new page begins inside a passage shown to the model, so it can
# cite the exact page. Brackets no answer would naturally contain.
MARKER = "⟪પાનું {page}⟫"
# How much of a page's opening text must be found in the chunk to place a
# marker; shorter openings are too ambiguous to locate.
_MARKER_PREFIX_CHARS = 24


def _pdf_path(doc_id: str):
    return config.UPLOAD_DIR / f"{doc_id}.pdf"


def _stored_path(doc_id: str):
    return config.PAGES_DIR / f"{doc_id}.json"


def save_book_pages(doc_id: str, pages) -> None:
    """Store the indexed text of every page (processing.pdf_extractor.Page)."""
    payload = {str(p.page_number): p.text for p in pages}
    _stored_path(doc_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    _book_pages.cache_clear()


def delete_book_pages(doc_id: str) -> None:
    _stored_path(doc_id).unlink(missing_ok=True)
    _book_pages.cache_clear()


@functools.lru_cache(maxsize=4)
def _book_pages(doc_id: str) -> Dict[int, str]:
    stored = _stored_path(doc_id)
    if stored.exists():
        return {int(k): v for k, v in json.loads(stored.read_text(encoding="utf-8")).items()}

    from processing import pdf_extractor

    pages = pdf_extractor.extract_pages(_pdf_path(doc_id), use_ocr=False)
    pages = pdf_extractor.strip_running_headers(pages)
    return {p.page_number: p.text for p in pages}


_ocr_cache: Dict[tuple, str] = {}


def pdf_page_text(doc_id: str, page: int) -> Optional[str]:
    """Text of one page of the uploaded book, or None if it cannot be read."""
    try:
        text = _book_pages(doc_id).get(page)
    except Exception as exc:  # missing upload, unreadable PDF
        logger.warning("Page text unavailable for %s: %s", doc_id, exc)
        return None
    if text or _stored_path(doc_id).exists():
        return text or None  # stored text is final: an empty page stays empty
    # A scanned page has no text layer; OCR just this page, once.
    key = (doc_id, page)
    if key not in _ocr_cache:
        from processing import pdf_extractor
        try:
            _ocr_cache[key] = pdf_extractor.clean_text(pdf_extractor.ocr_page(_pdf_path(doc_id), page))
        except Exception as exc:
            logger.warning("OCR of %s page %d failed: %s", doc_id, page, exc)
            _ocr_cache[key] = ""
    return _ocr_cache[key] or None


page_text_source: Callable[[str, int], Optional[str]] = pdf_page_text


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
