"""Original PDFs, in a private Supabase Storage bucket.

The backend only needs the PDF on disk while ingesting it. Afterwards the copy
in the bucket is the only one. The secret key bypasses all access rules, so it
must stay on the server.
"""
from __future__ import annotations

from pathlib import Path

import httpx

import config

BUCKET = "books"
# A book can reach MAX_UPLOAD_MB, and the upload may run on a slow connection.
_TIMEOUT = httpx.Timeout(30, write=300, read=120)


def object_name(doc_id: str) -> str:
    return f"{doc_id}.pdf"


def _headers() -> dict:
    if not (config.SUPABASE_URL and config.SUPABASE_SECRET):
        raise RuntimeError(
            "Supabase Storage is not configured. Set SS_SUPABASE_SECRET in backend/.env "
            "— see backend/.env.example."
        )
    return {"apikey": config.SUPABASE_SECRET,
            "Authorization": f"Bearer {config.SUPABASE_SECRET}"}


def _object_url(doc_id: str) -> str:
    return f"{config.SUPABASE_URL}/storage/v1/object/{BUCKET}/{object_name(doc_id)}"


def upload(doc_id: str, pdf_path: Path) -> str:
    """Store the PDF, streaming it from disk, and return its name in the bucket."""
    headers = {**_headers(), "Content-Type": "application/pdf", "x-upsert": "true"}
    with open(pdf_path, "rb") as fh:
        response = httpx.post(_object_url(doc_id), content=fh, headers=headers, timeout=_TIMEOUT)
    response.raise_for_status()
    return object_name(doc_id)


def download(doc_id: str) -> bytes:
    response = httpx.get(_object_url(doc_id), headers=_headers(), timeout=_TIMEOUT)
    response.raise_for_status()
    return response.content


def delete(doc_id: str) -> None:
    """Remove the PDF. Deleting one that isn't there is not an error."""
    response = httpx.request(
        "DELETE",
        f"{config.SUPABASE_URL}/storage/v1/object/{BUCKET}",
        json={"prefixes": [object_name(doc_id)]},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
