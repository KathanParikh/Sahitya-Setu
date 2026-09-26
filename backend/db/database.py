"""SQLite metadata store.

Holds everything that is not a vector: book records, detected chapters,
processing status and cached summaries. A fresh connection is opened per
operation because FastAPI runs upload processing on a background thread while
requests keep reading — SQLite connections are not safe to share across
threads, but the file is, in WAL mode.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

import config

_init_lock = threading.Lock()
_initialised = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id           TEXT PRIMARY KEY,
    filename         TEXT NOT NULL,
    title            TEXT,
    author           TEXT,
    page_count       INTEGER DEFAULT 0,
    chunk_count      INTEGER DEFAULT 0,
    chapter_count    INTEGER DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'pending',
    progress         TEXT,
    error            TEXT,
    file_path        TEXT,
    bm25_path        TEXT,
    extraction_stats TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id        TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chapter_index INTEGER NOT NULL,
    title         TEXT NOT NULL,
    start_page    INTEGER NOT NULL,
    end_page      INTEGER NOT NULL,
    UNIQUE (doc_id, chapter_index)
);

CREATE TABLE IF NOT EXISTS summaries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id        TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,              -- 'full' | 'chapter'
    chapter_index INTEGER NOT NULL DEFAULT -1,
    content       TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE (doc_id, kind, chapter_index)
);

CREATE TABLE IF NOT EXISTS evaluations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id     TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    metrics    TEXT NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chapters_doc ON chapters(doc_id);
CREATE INDEX IF NOT EXISTS idx_summaries_doc ON summaries(doc_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    global _initialised
    with _init_lock:
        if _initialised:
            return
        with connect() as conn:
            # WAL lets the API keep reading while a background upload writes.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
        _initialised = True


def _row_to_document(row: sqlite3.Row) -> Dict[str, Any]:
    doc = dict(row)
    stats = doc.get("extraction_stats")
    doc["extraction_stats"] = json.loads(stats) if stats else {}
    return doc


# ------------------------------------------------------------ documents ----
def create_document(doc_id: str, filename: str, file_path: str, title: str = "",
                    author: str = "") -> Dict[str, Any]:
    init_db()
    now = _now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO documents
               (doc_id, filename, title, author, status, file_path, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (doc_id, filename, title, author, file_path, now, now),
        )
    return get_document(doc_id)


def update_document(doc_id: str, **fields) -> None:
    if not fields:
        return
    if "extraction_stats" in fields and not isinstance(fields["extraction_stats"], str):
        fields["extraction_stats"] = json.dumps(fields["extraction_stats"], ensure_ascii=False)
    fields["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    with connect() as conn:
        conn.execute(
            f"UPDATE documents SET {assignments} WHERE doc_id = ?",
            (*fields.values(), doc_id),
        )


def set_status(doc_id: str, status: str, progress: str = None, error: str = None) -> None:
    fields: Dict[str, Any] = {"status": status}
    if progress is not None:
        fields["progress"] = progress
    if error is not None:
        fields["error"] = error
    update_document(doc_id, **fields)


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    return _row_to_document(row) if row else None


def list_documents() -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return [_row_to_document(r) for r in rows]


def delete_document(doc_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))


# ------------------------------------------------------------- chapters ----
def save_chapters(doc_id: str, chapters: List[Any]) -> None:
    """Replace the chapter list for a document (chapters is a list of Chapter)."""
    with connect() as conn:
        conn.execute("DELETE FROM chapters WHERE doc_id = ?", (doc_id,))
        conn.executemany(
            """INSERT INTO chapters (doc_id, chapter_index, title, start_page, end_page)
               VALUES (?, ?, ?, ?, ?)""",
            [(doc_id, c.index, c.title, c.start_page, c.end_page) for c in chapters],
        )


def get_chapters(doc_id: str) -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT chapter_index, title, start_page, end_page FROM chapters "
            "WHERE doc_id = ? ORDER BY chapter_index",
            (doc_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------ summaries ----
def save_summary(doc_id: str, kind: str, content: str, chapter_index: int = -1) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO summaries (doc_id, kind, chapter_index, content, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(doc_id, kind, chapter_index)
               DO UPDATE SET content = excluded.content, created_at = excluded.created_at""",
            (doc_id, kind, chapter_index, content, _now()),
        )


def get_summary(doc_id: str, kind: str, chapter_index: int = -1) -> Optional[str]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT content FROM summaries WHERE doc_id = ? AND kind = ? AND chapter_index = ?",
            (doc_id, kind, chapter_index),
        ).fetchone()
    return row["content"] if row else None


def get_chapter_summaries(doc_id: str) -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """SELECT s.chapter_index, s.content, c.title, c.start_page, c.end_page
               FROM summaries s
               LEFT JOIN chapters c
                 ON c.doc_id = s.doc_id AND c.chapter_index = s.chapter_index
               WHERE s.doc_id = ? AND s.kind = 'chapter'
               ORDER BY s.chapter_index""",
            (doc_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_summaries(doc_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM summaries WHERE doc_id = ?", (doc_id,))


# ---------------------------------------------------------- evaluations ----
def save_evaluation(doc_id: str, metrics: Dict[str, Any], sample_count: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO evaluations (doc_id, metrics, sample_count, created_at) VALUES (?, ?, ?, ?)",
            (doc_id, json.dumps(metrics, ensure_ascii=False), sample_count, _now()),
        )


def get_latest_evaluation(doc_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM evaluations WHERE doc_id = ? ORDER BY id DESC LIMIT 1", (doc_id,)
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["metrics"] = json.loads(out["metrics"])
    return out
