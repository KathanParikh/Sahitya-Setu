"""Chunk and vector storage in Postgres, using pgvector.

All books share the chunks table, so every query filters by doc_id: a question
about book A can never surface a chunk from book B. Search is exact rather than
through an HNSW index, which would look across all books and filter afterwards,
sometimes returning fewer than top_k. A book has only a few hundred chunks, so
comparing against all of them is fast.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import config
from db import database

_COLUMNS = """chunk_id, text, chunk_index, page_start, page_end, chapter_index,
              chapter_title, token_count"""


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def _to_row(record: dict) -> dict:
    row = {"chunk_id": record["chunk_id"], "text": record["text"]}
    row["metadata"] = {
        key: record[key]
        for key in ("chunk_index", "page_start", "page_end", "chapter_index",
                    "chapter_title", "token_count")
    }
    return row


def add_chunks(doc_id: str, chunks: Sequence, embeddings: Sequence[Sequence[float]]) -> int:
    """Insert chunks and their vectors. Chunks and embeddings must align."""
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings length mismatch")
    if not chunks:
        return 0

    # One transaction: a failure leaves no half-indexed book behind.
    with database.connect() as conn, conn.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO chunks
               (doc_id, chunk_id, chunk_index, text, page_start, page_end,
                chapter_index, chapter_title, token_count, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::extensions.vector)""",
            [
                (doc_id, c.chunk_id, c.chunk_index, c.text, c.page_start, c.page_end,
                 c.chapter_index, c.chapter_title, c.token_count, _vector_literal(e))
                for c, e in zip(chunks, embeddings)
            ],
        )
    return len(chunks)


def search(doc_id: str, query_embedding: Sequence[float], top_k: int = None) -> List[dict]:
    """Vector search. Returns rows with chunk_id, text, metadata, score, rank."""
    top_k = top_k or config.VECTOR_TOP_K
    with database.connect() as conn:
        records = conn.execute(
            f"""SELECT {_COLUMNS},
                       embedding OPERATOR(extensions.<=>) %s::extensions.vector AS distance
                FROM chunks
                WHERE doc_id = %s
                ORDER BY distance, chunk_index
                LIMIT %s""",
            (_vector_literal(query_embedding), doc_id, top_k),
        ).fetchall()

    rows: List[dict] = []
    for rank, record in enumerate(records, start=1):
        row = _to_row(record)
        # Cosine distance -> similarity, purely for display.
        row["score"] = 1.0 - float(record["distance"])
        row["rank"] = rank
        rows.append(row)
    return rows


def get_by_ids(doc_id: str, chunk_ids: Sequence[str]) -> Dict[str, dict]:
    """Fetch chunks by id — how BM25 hits are hydrated into full passages."""
    if not chunk_ids:
        return {}
    with database.connect() as conn:
        records = conn.execute(
            f"SELECT {_COLUMNS} FROM chunks WHERE doc_id = %s AND chunk_id = ANY(%s)",
            (doc_id, list(chunk_ids)),
        ).fetchall()
    return {record["chunk_id"]: _to_row(record) for record in records}


def get_all_chunks(doc_id: str) -> List[dict]:
    """Every chunk in reading order — the input to summarisation and BM25."""
    with database.connect() as conn:
        records = conn.execute(
            f"SELECT {_COLUMNS} FROM chunks WHERE doc_id = %s ORDER BY chunk_index",
            (doc_id,),
        ).fetchall()
    return [_to_row(record) for record in records]


def delete_document(doc_id: str) -> None:
    with database.connect() as conn:
        conn.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
