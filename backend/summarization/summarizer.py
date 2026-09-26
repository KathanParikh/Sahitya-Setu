"""Hierarchical summarisation: chunks -> chapter summaries -> book summary.

A Gujarati novel is far longer than any free-tier context window, so the
summary is built bottom-up. Chunks of a chapter are grouped into batches that
fit comfortably in one request (map), those partial summaries are condensed
into one chapter summary (reduce), and the chapter summaries are condensed
again into the whole-book summary. The book summary therefore never sees raw
text — only text the model has already read once, which keeps it consistent
with the per-chapter output shown next to it.

Results are cached in SQLite: summarising a full book costs dozens of LLM
calls and must not be repeated on every page load.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Sequence

import config
from db import database
from indexing import vector_store
from qa.llm_client import BaseLLM, LLMError, get_llm

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM = """You are a literary summariser for Gujarati books.

You summarise only what the supplied text says. You never add events, characters,
interpretations or context that are not present in the text. If the text is fragmentary,
your summary is correspondingly brief."""


def _language_clause(language: str) -> str:
    return ("ઉત્તર ગુજરાતીમાં જ આપો." if language == "gujarati"
            else "Write the summary in English.")


def _map_prompt(text: str, language: str) -> str:
    return (
        f"Book text:\n\n{text}\n\n===\n\n"
        "Summarise the passage above. Keep every named character, place, and event that "
        "appears. Do not add anything that is not in the text. Write 4-8 sentences of "
        f"continuous prose, not bullet points.\n{_language_clause(language)}"
    )


def _reduce_prompt(parts: Sequence[str], label: str, language: str) -> str:
    joined = "\n\n".join(f"[{i}] {p}" for i, p in enumerate(parts, start=1))
    return (
        f"Partial summaries of {label}, in reading order:\n\n{joined}\n\n===\n\n"
        f"Combine these into one coherent summary of {label}. Preserve the narrative order, "
        "keep the named characters and key events, remove repetition, and add nothing new. "
        f"Write 6-12 sentences of continuous prose.\n{_language_clause(language)}"
    )


def _book_prompt(chapter_summaries: Sequence[str], title: str, language: str) -> str:
    joined = "\n\n".join(f"Chapter {i}: {s}" for i, s in enumerate(chapter_summaries, start=1))
    name = title or "this book"
    return (
        f"Chapter summaries of {name}, in order:\n\n{joined}\n\n===\n\n"
        f"Write a summary of {name} as a whole, based only on the chapter summaries above. "
        "Cover the main storyline or argument from beginning to end, the principal characters, "
        "and how it concludes. Add no interpretation that the summaries do not support. "
        f"Write 3-5 paragraphs.\n{_language_clause(language)}"
    )


# --------------------------------------------------------------- batching --
def _batch_by_tokens(rows: Sequence[dict], budget: int) -> List[List[dict]]:
    """Group chunk rows into batches of roughly `budget` tokens."""
    batches: List[List[dict]] = []
    current: List[dict] = []
    total = 0
    for row in rows:
        tokens = int((row.get("metadata") or {}).get("token_count", 0)) or \
            max(1, len(row.get("text", "")) // 3)
        if current and total + tokens > budget:
            batches.append(current)
            current, total = [], 0
        current.append(row)
        total += tokens
    if current:
        batches.append(current)
    return batches


def _throttle() -> None:
    if config.SUMMARY_REQUEST_DELAY > 0:
        time.sleep(config.SUMMARY_REQUEST_DELAY)


def _summarise_rows(rows: Sequence[dict], label: str, language: str, llm: BaseLLM) -> str:
    """Map over token-budgeted batches, then reduce if there was more than one."""
    if not rows:
        return ""

    batches = _batch_by_tokens(rows, config.SUMMARY_MAP_BATCH_TOKENS)
    partials: List[str] = []
    for i, batch in enumerate(batches):
        text = "\n\n".join(r.get("text", "") for r in batch)
        if not text.strip():
            continue
        logger.info("summarising %s: batch %d/%d", label, i + 1, len(batches))
        partials.append(llm.generate(_map_prompt(text, language), system=SUMMARY_SYSTEM))
        if i < len(batches) - 1:
            _throttle()

    if not partials:
        return ""
    if len(partials) == 1:
        return partials[0]

    _throttle()
    return llm.generate(_reduce_prompt(partials, label, language), system=SUMMARY_SYSTEM)


# ------------------------------------------------------ public interface ---
def summarize_chapters(
    doc_id: str,
    language: Optional[str] = None,
    force: bool = False,
    llm: Optional[BaseLLM] = None,
) -> List[Dict[str, Any]]:
    """Summarise every chapter, using the cache unless `force` is set."""
    language = language or config.SUMMARY_LANGUAGE
    llm = llm or get_llm()

    chapters = database.get_chapters(doc_id)
    rows = vector_store.get_all_chunks(doc_id)
    if not rows:
        raise ValueError(f"No indexed content for document {doc_id}")

    if not chapters:
        # Books with no detectable chapter headings still get a sectioned
        # summary, split by position so the reader gets more than one blob.
        return _summarize_sections(doc_id, rows, language, force, llm)

    cached = {s["chapter_index"]: s["content"]
              for s in database.get_chapter_summaries(doc_id)} if not force else {}

    results: List[Dict[str, Any]] = []
    for chapter in chapters:
        index = chapter["chapter_index"]
        if index in cached:
            results.append({**chapter, "summary": cached[index], "cached": True})
            continue

        chapter_rows = [r for r in rows
                        if (r.get("metadata") or {}).get("chapter_index") == index]
        if not chapter_rows:
            continue

        summary = _summarise_rows(chapter_rows, f"chapter '{chapter['title']}'", language, llm)
        if summary:
            database.save_summary(doc_id, "chapter", summary, chapter_index=index)
        results.append({**chapter, "summary": summary, "cached": False})
        _throttle()

    return results


def _summarize_sections(doc_id: str, rows: Sequence[dict], language: str,
                        force: bool, llm: BaseLLM) -> List[Dict[str, Any]]:
    """Fallback for unstructured books: summarise in fixed-size sections."""
    cached = {s["chapter_index"]: s["content"]
              for s in database.get_chapter_summaries(doc_id)} if not force else {}
    batches = _batch_by_tokens(rows, config.SUMMARY_MAP_BATCH_TOKENS * 2)

    results: List[Dict[str, Any]] = []
    for i, batch in enumerate(batches):
        pages = [int((r.get("metadata") or {}).get("page_start", 0)) for r in batch]
        entry = {
            "chapter_index": i,
            "title": f"Section {i + 1} (pages {min(pages)}-{max(pages)})" if pages
                     else f"Section {i + 1}",
            "start_page": min(pages) if pages else 0,
            "end_page": max(pages) if pages else 0,
        }
        if i in cached:
            results.append({**entry, "summary": cached[i], "cached": True})
            continue
        summary = _summarise_rows(batch, entry["title"], language, llm)
        if summary:
            database.save_summary(doc_id, "chapter", summary, chapter_index=i)
        results.append({**entry, "summary": summary, "cached": False})
        _throttle()
    return results


def summarize_book(
    doc_id: str,
    language: Optional[str] = None,
    force: bool = False,
    llm: Optional[BaseLLM] = None,
) -> Dict[str, Any]:
    """Full-book summary, built on top of the chapter summaries."""
    language = language or config.SUMMARY_LANGUAGE
    llm = llm or get_llm()

    if not force:
        cached = database.get_summary(doc_id, "full")
        if cached:
            return {"doc_id": doc_id, "summary": cached, "cached": True}

    document = database.get_document(doc_id) or {}
    chapters = summarize_chapters(doc_id, language=language, force=force, llm=llm)
    parts = [c["summary"] for c in chapters if c.get("summary")]
    if not parts:
        raise ValueError(f"Nothing to summarise for document {doc_id}")

    _throttle()
    title = document.get("title") or document.get("filename") or ""
    if len(parts) == 1:
        # A single-chapter book needs no second reduction pass.
        summary = parts[0]
    else:
        summary = llm.generate(_book_prompt(parts, title, language), system=SUMMARY_SYSTEM)

    database.save_summary(doc_id, "full", summary)
    return {
        "doc_id": doc_id,
        "summary": summary,
        "cached": False,
        "built_from_chapters": len(parts),
    }
