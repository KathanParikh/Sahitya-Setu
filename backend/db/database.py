"""Postgres metadata store (Supabase).

Holds book records, detected chapters, processing status, page text, cached
summaries and evaluation reports. The tables are defined in schema.sql. Connections come from
a small pool, because opening one takes far longer than a query and the
background upload thread and API requests all need them at the same time.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

import config

_pool_lock = threading.Lock()
_pool: Optional[ConnectionPool] = None


def _get_pool() -> ConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            if not config.DATABASE_URL:
                raise RuntimeError(
                    "SS_DATABASE_URL is not set. Put the Supabase session pooler "
                    "address in backend/.env — see backend/.env.example."
                )
            _pool = ConnectionPool(
                config.DATABASE_URL,
                min_size=1,
                max_size=4,
                timeout=30,
                kwargs={"row_factory": dict_row, "connect_timeout": 15},
                # The pooler drops idle connections, so test each one before use.
                check=ConnectionPool.check_connection,
                open=True,
            )
        return _pool


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """A pooled connection: commits on success, rolls back on an exception."""
    with _get_pool().connection() as conn:
        yield conn


def init_db() -> None:
    """Fail at startup, with a clear message, if the database can't be reached."""
    with connect() as conn:
        conn.execute("SELECT 1")


def close_db() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


# ------------------------------------------------------------ documents ----
def create_document(doc_id: str, filename: str, file_path: str, title: str = "",
                    author: str = "", user_id: Optional[str] = None) -> Dict[str, Any]:
    with connect() as conn:
        conn.execute(
            """INSERT INTO documents (doc_id, user_id, filename, title, author, status, file_path)
               VALUES (%s, %s, %s, %s, %s, 'pending', %s)""",
            (doc_id, user_id, filename, title, author, file_path),
        )
    return get_document(doc_id)


def update_document(doc_id: str, **fields) -> None:
    if not fields:
        return
    if "extraction_stats" in fields:
        fields["extraction_stats"] = Jsonb(fields["extraction_stats"])
    assignments = ", ".join(f"{key} = %s" for key in fields)
    with connect() as conn:
        conn.execute(
            f"UPDATE documents SET {assignments}, updated_at = now() WHERE doc_id = %s",
            (*fields.values(), doc_id),
        )


def set_status(doc_id: str, status: str, progress: str = None, error: str = None) -> None:
    fields: Dict[str, Any] = {"status": status}
    if progress is not None:
        fields["progress"] = progress
    if error is not None:
        fields["error"] = error
    update_document(doc_id, **fields)


def fail_interrupted_documents(doc_id: Optional[str] = None) -> int:
    """Mark books left mid-ingestion by a server restart as failed.

    Ingestion runs inside the server process, so a restart kills it while the
    row still says 'processing', and the book would wait forever. Assumes one
    server process, so nothing is really running when this is called at startup.
    Passing doc_id limits it to that book.
    """
    with connect() as conn:
        cursor = conn.execute(
            """UPDATE documents
               SET status = 'failed', progress = 'failed', updated_at = now(),
                   error = 'The server restarted during processing. Please upload the book again.'
               WHERE status IN ('pending', 'processing')
                 AND (%(doc_id)s::text IS NULL OR doc_id = %(doc_id)s)""",
            {"doc_id": doc_id},
        )
        return cursor.rowcount


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        return conn.execute("SELECT * FROM documents WHERE doc_id = %s", (doc_id,)).fetchone()


def list_documents(user_id: str) -> List[Dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM documents WHERE user_id = %s ORDER BY created_at DESC", (user_id,)
        ).fetchall()


def delete_document(doc_id: str) -> None:
    """Delete a book; its chapters, summaries and other rows cascade with it."""
    with connect() as conn:
        conn.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))


# ------------------------------------------------------------- chapters ----
def save_chapters(doc_id: str, chapters: List[Any]) -> None:
    """Replace the chapter list for a document (chapters is a list of Chapter)."""
    with connect() as conn:
        conn.execute("DELETE FROM chapters WHERE doc_id = %s", (doc_id,))
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO chapters (doc_id, chapter_index, title, start_page, end_page)
                   VALUES (%s, %s, %s, %s, %s)""",
                [(doc_id, c.index, c.title, c.start_page, c.end_page) for c in chapters],
            )


def get_chapters(doc_id: str) -> List[Dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT chapter_index, title, start_page, end_page FROM chapters "
            "WHERE doc_id = %s ORDER BY chapter_index",
            (doc_id,),
        ).fetchall()


# ------------------------------------------------------------ summaries ----
def save_summary(doc_id: str, kind: str, content: str, chapter_index: int = -1) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO summaries (doc_id, kind, chapter_index, content)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (doc_id, kind, chapter_index)
               DO UPDATE SET content = excluded.content, created_at = now()""",
            (doc_id, kind, chapter_index, content),
        )


def get_summary(doc_id: str, kind: str, chapter_index: int = -1) -> Optional[str]:
    with connect() as conn:
        row = conn.execute(
            "SELECT content FROM summaries WHERE doc_id = %s AND kind = %s AND chapter_index = %s",
            (doc_id, kind, chapter_index),
        ).fetchone()
    return row["content"] if row else None


def get_chapter_summaries(doc_id: str) -> List[Dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            """SELECT s.chapter_index, s.content, c.title, c.start_page, c.end_page
               FROM summaries s
               LEFT JOIN chapters c
                 ON c.doc_id = s.doc_id AND c.chapter_index = s.chapter_index
               WHERE s.doc_id = %s AND s.kind = 'chapter'
               ORDER BY s.chapter_index""",
            (doc_id,),
        ).fetchall()


# ---------------------------------------------------------------- pages ----
def save_pages(doc_id: str, pages: List[Any]) -> None:
    """Replace a book's page text (pages is a list of pdf_extractor.Page)."""
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM pages WHERE doc_id = %s", (doc_id,))
        cursor.executemany(
            "INSERT INTO pages (doc_id, page_number, text, source) VALUES (%s, %s, %s, %s)",
            [(doc_id, p.page_number, p.text, p.source) for p in pages],
        )


def get_pages(doc_id: str) -> Dict[int, str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT page_number, text FROM pages WHERE doc_id = %s", (doc_id,)
        ).fetchall()
    return {row["page_number"]: row["text"] for row in rows}


def delete_pages(doc_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM pages WHERE doc_id = %s", (doc_id,))


# ---------------------------------------------------------- evaluations ----
def save_evaluation(doc_id: str, metrics: Dict[str, Any], sample_count: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO evaluations (doc_id, metrics, sample_count) VALUES (%s, %s, %s)",
            (doc_id, Jsonb(metrics), sample_count),
        )


def get_latest_evaluation(doc_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM evaluations WHERE doc_id = %s ORDER BY id DESC LIMIT 1", (doc_id,)
        ).fetchone()
