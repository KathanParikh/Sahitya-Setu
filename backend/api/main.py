"""FastAPI application — every HTTP route for Sahitya Setu.

Ingestion (extract -> chunk -> embed -> index) runs on a background thread:
embedding a few hundred pages with multilingual-e5-base on CPU takes minutes,
far past any browser's timeout. The upload call returns a doc_id immediately
and the client polls /api/documents/{doc_id} for status.
"""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from db import database
from indexing import bm25_index, embedder, vector_store
from processing import chunker, pdf_extractor
from qa.graph import answer_question
from qa.llm_client import configured_providers
from summarization import summarizer

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sahitya_setu")

@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    logger.info("Sahitya Setu ready. LLM provider: %s", config.LLM_PROVIDER)
    yield


app = FastAPI(
    title="Sahitya Setu",
    description="Grounded question answering and summarisation over Gujarati books.",
    version="1.0.0",
    lifespan=lifespan,
)

_origins = [o.strip() for o in config.CORS_ORIGINS if o.strip()]
if "*" in _origins:
    # A literal ["*"] list plus credentials is rejected by every browser, so the
    # wildcard is expressed as a regex, which echoes the caller's own origin
    # back. Set SS_CORS_ORIGINS=* only for local development.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ------------------------------------------------------------- schemas ----
class AskRequest(BaseModel):
    doc_id: str = Field(..., description="id returned by /api/upload")
    question: str = Field(..., min_length=1, description="question in Gujarati or English")


class UploadResponse(BaseModel):
    doc_id: str
    status: str
    filename: str
    message: str
    # Populated only for ?wait=true, which runs ingestion inline so the upload
    # response itself can be eyeballed instead of polled for.
    pages: Optional[int] = None
    chunks: Optional[int] = None
    chapters_found: Optional[List[str]] = None
    sample_chunks: Optional[List[Dict[str, Any]]] = None


# ------------------------------------------------------- ingestion job ----
def process_document(doc_id: str, pdf_path: Path, use_ocr: bool = True,
                     original_name: str = "") -> None:
    """The full ingestion pipeline. Runs in the background; never raises out."""
    try:
        database.set_status(doc_id, "processing", progress="extracting text")
        pages = pdf_extractor.extract_pages(pdf_path, use_ocr=use_ocr)
        # Strip the folio and book title printed on every page before anything
        # downstream sees them; otherwise they land mid-sentence in any chunk
        # that spans a page break.
        pages = pdf_extractor.strip_running_headers(pages)
        stats = pdf_extractor.extraction_stats(pages)
        logger.info("[%s] extracted %s", doc_id, stats)

        if stats["total_characters"] == 0:
            raise ValueError(
                "No text could be extracted. If this is a scanned book, install "
                "Tesseract with the Gujarati language pack (brew install tesseract "
                "tesseract-lang) and poppler."
            )

        database.set_status(doc_id, "processing", progress="detecting chapters")
        chapters = chunker.detect_chapters(pages)
        database.save_chapters(doc_id, chapters)
        logger.info("[%s] detected %d chapters", doc_id, len(chapters))

        database.set_status(doc_id, "processing", progress="chunking")
        chunks = chunker.chunk_document(doc_id, pages, chapters)
        if not chunks:
            raise ValueError("Chunking produced no chunks — the PDF appears to be empty.")
        logger.info("[%s] %s", doc_id, chunker.chunking_stats(chunks))

        database.set_status(
            doc_id, "processing",
            progress=f"embedding {len(chunks)} chunks (this is the slow step)",
        )
        embeddings = embedder.embed_passages([c.text for c in chunks], show_progress=True)

        database.set_status(doc_id, "processing", progress="building vector index")
        # Re-uploading the same file id must not double-index it.
        vector_store.delete_document(doc_id)
        vector_store.add_chunks(doc_id, chunks, embeddings)

        database.set_status(doc_id, "processing", progress="building keyword index")
        bm25_path = bm25_index.build_and_save(doc_id, chunks)

        meta = pdf_extractor.extract_metadata(pdf_path)
        database.update_document(
            doc_id,
            # The file on disk is named after the doc_id, so fall back to the
            # name the reader uploaded rather than a hex string.
            title=meta.get("title") or Path(original_name or pdf_path).stem,
            author=meta.get("author", ""),
            page_count=stats["total_pages"],
            chunk_count=len(chunks),
            chapter_count=len(chapters),
            bm25_path=str(bm25_path),
            extraction_stats=stats,
            status="ready",
            progress="ready",
            error=None,
        )
        logger.info("[%s] ready: %d chunks, %d chapters", doc_id, len(chunks), len(chapters))

    except Exception as exc:
        logger.exception("[%s] ingestion failed", doc_id)
        database.set_status(doc_id, "failed", progress="failed", error=str(exc)[:1000])


def _sample_chunks(doc_id: str, count: int) -> List[Dict[str, Any]]:
    """The first chunks in reading order, for spot-checking an ingestion.

    Page numbers, the attached chapter and the Gujarati itself are all things
    that have to be eyeballed once per new book format.
    """
    return [
        {
            "chunk_id": row["chunk_id"],
            "text": row["text"],
            "page_start": row["metadata"].get("page_start"),
            "page_end": row["metadata"].get("page_end"),
            "chapter_title": row["metadata"].get("chapter_title") or None,
            "token_count": row["metadata"].get("token_count"),
        }
        for row in vector_store.get_all_chunks(doc_id)[:count]
    ]


def _require_llm() -> None:
    """Fail fast and legibly when no provider key is set.

    Without this the missing key surfaces deep inside the graph as a 500,
    which is a miserable first-run experience.
    """
    if not configured_providers():
        raise HTTPException(
            503,
            "No LLM provider is configured. Put GEMINI_API_KEY (or GROQ_API_KEY) "
            "in backend/.env — see backend/.env.example.",
        )


def _require_ready(doc_id: str) -> Dict[str, Any]:
    document = database.get_document(doc_id)
    if not document:
        raise HTTPException(404, f"Unknown document '{doc_id}'.")
    if document["status"] != "ready":
        raise HTTPException(
            409,
            f"Document is '{document['status']}' ({document.get('progress') or ''}). "
            f"{document.get('error') or 'Wait for processing to finish.'}",
        )
    return document


# --------------------------------------------------------------- routes ---
@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "llm_provider": config.LLM_PROVIDER,
        "llm_model": config.GEMINI_MODEL if config.LLM_PROVIDER == "gemini" else config.GROQ_MODEL,
        "embedding_model": config.EMBEDDING_MODEL,
        "gemini_key_set": bool(config.GEMINI_API_KEY),
        "groq_key_set": bool(config.GROQ_API_KEY),
        "documents": len(database.list_documents()),
    }


@app.post("/api/upload", response_model=UploadResponse)
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    use_ocr: bool = Query(True, description="set false to skip OCR on image-only pages"),
    wait: bool = Query(False, description="ingest inline and return counts instead of polling"),
) -> UploadResponse:
    """Accept a PDF and ingest it.

    By default ingestion runs in the background and the client polls
    /api/documents/{doc_id}: embedding a few hundred pages takes minutes, past
    any browser timeout. `?wait=true` runs the same pipeline inline and returns
    the page/chunk/chapter counts plus a few chunks in the response, which is
    what the curl smoke test and small books want.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    doc_id = uuid.uuid4().hex[:12]
    destination = config.UPLOAD_DIR / f"{doc_id}.pdf"

    size = 0
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    try:
        with open(destination, "wb") as out:
            # Stream to disk in chunks so a large book never sits in memory.
            while block := await file.read(1024 * 1024):
                size += len(block)
                if size > limit:
                    raise HTTPException(413, f"File exceeds {config.MAX_UPLOAD_MB} MB.")
                out.write(block)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    database.create_document(doc_id, file.filename, str(destination))

    if wait:
        # The pipeline is blocking CPU work, so it cannot run on the event loop.
        await run_in_threadpool(process_document, doc_id, destination, use_ocr, file.filename)
        document = database.get_document(doc_id)
        if not document or document["status"] != "ready":
            raise HTTPException(500, (document or {}).get("error") or "Ingestion failed.")
        return UploadResponse(
            doc_id=doc_id,
            status="ready",
            filename=file.filename,
            message="Ingestion complete.",
            pages=document["page_count"],
            chunks=document["chunk_count"],
            chapters_found=[c["title"] for c in database.get_chapters(doc_id)],
            sample_chunks=_sample_chunks(doc_id, 3),
        )

    background_tasks.add_task(process_document, doc_id, destination, use_ocr, file.filename)
    return UploadResponse(
        doc_id=doc_id,
        status="processing",
        filename=file.filename,
        message="Upload received. Poll /api/documents/{doc_id} until status is 'ready'.",
    )


@app.get("/api/documents")
def list_documents() -> List[Dict[str, Any]]:
    return database.list_documents()


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str, samples: int = Query(0, ge=0, le=20)) -> Dict[str, Any]:
    """Document record, its chapters, and optionally a few chunks to eyeball.

    `?samples=3` returns the first chunks in reading order so the ingestion can
    be spot-checked by hand — that page numbers line up, that a chapter was
    attached, that the Gujarati came through clean.
    """
    document = database.get_document(doc_id)
    if not document:
        raise HTTPException(404, f"Unknown document '{doc_id}'.")

    chapters = database.get_chapters(doc_id)
    document["chapters"] = chapters
    document["chapters_found"] = [c["title"] for c in chapters]

    if samples:
        document["sample_chunks"] = _sample_chunks(doc_id, samples)
    return document


# The singular spelling is what the Step 1 contract and the curl examples use.
@app.get("/api/document/{doc_id}", include_in_schema=False)
def get_document_alias(doc_id: str, samples: int = Query(0, ge=0, le=20)) -> Dict[str, Any]:
    return get_document(doc_id, samples=samples)


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str) -> Dict[str, str]:
    document = database.get_document(doc_id)
    if not document:
        raise HTTPException(404, f"Unknown document '{doc_id}'.")

    vector_store.delete_document(doc_id)
    bm25_index.delete_index(doc_id)
    if document.get("file_path"):
        Path(document["file_path"]).unlink(missing_ok=True)
    database.delete_document(doc_id)
    return {"doc_id": doc_id, "status": "deleted"}


@app.post("/api/ask")
def ask(request: AskRequest) -> Dict[str, Any]:
    """Answer a question strictly from one uploaded book."""
    _require_ready(request.doc_id)
    _require_llm()
    try:
        result = answer_question(request.doc_id, request.question.strip())
    except Exception as exc:
        logger.exception("QA failed")
        raise HTTPException(500, f"Question answering failed: {exc}")

    if result.get("llm_error"):
        # Never report "not found in the book" when the truth is that the
        # model could not be reached — that would be a refusal we did not earn.
        raise HTTPException(
            503, f"The language model could not be reached: {result['llm_error']}"
        )
    return result


@app.get("/api/summary/{doc_id}")
def summary(
    doc_id: str,
    force: bool = Query(False, description="ignore the cached summary and rebuild"),
    language: Optional[str] = Query(None, pattern="^(gujarati|english)$"),
) -> Dict[str, Any]:
    """Full-book summary, built hierarchically from the chapter summaries."""
    _require_ready(doc_id)
    _require_llm()
    try:
        return summarizer.summarize_book(doc_id, language=language, force=force)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Summarisation failed")
        raise HTTPException(500, f"Summarisation failed: {exc}")


@app.get("/api/summary/{doc_id}/chapters")
def chapter_summaries(
    doc_id: str,
    force: bool = Query(False, description="ignore cached summaries and rebuild"),
    language: Optional[str] = Query(None, pattern="^(gujarati|english)$"),
) -> Dict[str, Any]:
    """One summary per detected chapter."""
    _require_ready(doc_id)
    _require_llm()
    try:
        chapters = summarizer.summarize_chapters(doc_id, language=language, force=force)
        return {"doc_id": doc_id, "chapter_count": len(chapters), "chapters": chapters}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Chapter summarisation failed")
        raise HTTPException(500, f"Chapter summarisation failed: {exc}")


@app.get("/api/evaluate/{doc_id}")
def evaluate(
    doc_id: str,
    limit: Optional[int] = Query(None, ge=1, description="run only the first N test cases"),
    cached: bool = Query(False, description="return the last stored report instead of re-running"),
) -> Dict[str, Any]:
    """Run the RAGAS evaluation suite against this document's test set.

    This is slow — every case is a full pipeline run plus judge calls — so the
    last report is stored and can be re-read with ?cached=true.
    """
    _require_ready(doc_id)

    if cached:
        report = database.get_latest_evaluation(doc_id)
        if not report:
            raise HTTPException(404, "No stored evaluation for this document yet.")
        return report["metrics"]

    # Imported lazily: RAGAS pulls in a large dependency tree that should not
    # slow down or break server startup for users who never evaluate.
    _require_llm()
    from evaluation.ragas_eval import evaluate_document

    try:
        return evaluate_document(doc_id, limit=limit)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Evaluation failed")
        raise HTTPException(500, f"Evaluation failed: {exc}")
