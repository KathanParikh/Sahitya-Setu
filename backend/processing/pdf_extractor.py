"""PDF text extraction for digital and scanned Gujarati books.

Strategy: PyMuPDF first, page by page. Any page whose embedded text layer is
too thin to be real text is assumed to be a scan and is re-read with Tesseract
(lang=guj). Mixed books — a digital body with a scanned cover or plates — are
therefore handled without the caller choosing a mode.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

import config

logger = logging.getLogger(__name__)


@dataclass
class Page:
    page_number: int  # 1-indexed, matches what a reader sees
    text: str
    source: str  # "digital" | "ocr" | "empty"

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------- cleaning ---
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"), None)
# Control characters, minus the tab/newline we keep. PDFs that embed a legacy
# non-Unicode Gujarati font map every glyph to .notdef, and PyMuPDF renders
# that as NUL; without this the "text" of such a page is a run of \x00 that
# pollutes both the BM25 tokens and the embedding.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffd]")
_MULTI_SPACE = re.compile(r"[ \t ]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
# A hyphen at end of line is a word broken across lines in Latin text.
_LINE_BREAK_HYPHEN = re.compile(r"(\w)-\n(\w)")


def clean_text(text: str) -> str:
    """Normalise Unicode and collapse the whitespace noise PDFs are full of.

    NFC normalisation matters for Gujarati: the same syllable can arrive as a
    base letter plus a combining matra or as a single composed codepoint, and
    BM25 would treat the two spellings as different tokens.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    # Zero-width joiners are meaningful inside Indic clusters in theory, but
    # PDF producers sprinkle them arbitrarily; removing them makes tokens
    # comparable. NFC has already composed the real clusters.
    text = text.translate(_ZERO_WIDTH)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _LINE_BREAK_HYPHEN.sub(r"\1\2", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def _meaningful_char_count(text: str) -> int:
    """Count characters that are actual script, ignoring whitespace and digits.

    A scanned page often still carries a stray page number or a watermark in
    its text layer; counting only letters keeps those from looking like text.
    """
    return sum(1 for ch in text if ch.isalpha())


# ------------------------------------------------------------------- ocr ----
_ocr_ready: Optional[bool] = None


def _ensure_ocr() -> bool:
    """Import and configure the OCR stack once, returning whether it works."""
    global _ocr_ready
    if _ocr_ready is not None:
        return _ocr_ready
    try:
        import pytesseract
        from pdf2image import convert_from_path  # noqa: F401

        if config.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
        installed = set(pytesseract.get_languages(config=""))
        # OCR_LANG may be a "+"-joined spec such as "guj+eng"; every part of it
        # needs its own traineddata file before Tesseract will accept the pass.
        missing = [p for p in config.OCR_LANG.split("+") if p and p not in installed]
        if missing:
            logger.warning(
                "Tesseract is installed but the %s language pack(s) are missing "
                "(found: %s). Scanned pages will be skipped.",
                ", ".join(f"'{m}'" for m in missing), ", ".join(sorted(installed)[:10]),
            )
            _ocr_ready = False
        else:
            _ocr_ready = True
    except Exception as exc:  # ImportError, TesseractNotFound, poppler missing
        logger.warning("OCR unavailable (%s). Scanned pages will be skipped.", exc)
        _ocr_ready = False
    return _ocr_ready


def ocr_page(pdf_path: Path, page_number: int) -> str:
    """Rasterise one page and run Tesseract over it."""
    import pytesseract
    from pdf2image import convert_from_path

    kwargs = {
        "dpi": config.OCR_DPI,
        "first_page": page_number,
        "last_page": page_number,
    }
    if config.POPPLER_PATH:
        kwargs["poppler_path"] = config.POPPLER_PATH
    images = convert_from_path(str(pdf_path), **kwargs)
    if not images:
        return ""
    return pytesseract.image_to_string(images[0], lang=config.OCR_LANG)


# ------------------------------------------------------------ extraction ----
def _pymupdf():
    """Import PyMuPDF under whichever name this version exposes.

    The package renamed its module from `fitz` to `pymupdf` in 1.24 and warns
    on the old name; both spellings are still shipped.
    """
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz


def extract_pages(pdf_path: str | Path, use_ocr: bool = True) -> List[Page]:
    """Extract one Page per PDF page, OCR-ing the pages that need it.

    Args:
        pdf_path: path to the PDF on disk.
        use_ocr: set False to force digital-only extraction (faster, and what
            the demo path uses for clean digital PDFs).
    """
    fitz = _pymupdf()

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages: List[Page] = []
    doc = fitz.open(str(pdf_path))
    try:
        for index in range(doc.page_count):
            raw = doc.load_page(index).get_text("text")
            text = clean_text(raw)
            source = "digital"

            if _meaningful_char_count(text) < config.DIGITAL_TEXT_MIN_CHARS:
                if use_ocr and _ensure_ocr():
                    try:
                        ocr_text = clean_text(ocr_page(pdf_path, index + 1))
                        if _meaningful_char_count(ocr_text) > _meaningful_char_count(text):
                            text, source = ocr_text, "ocr"
                        else:
                            source = "empty" if not text else "digital"
                    except Exception as exc:
                        logger.warning("OCR failed on page %d: %s", index + 1, exc)
                        source = "empty" if not text else "digital"
                else:
                    source = "empty" if not text else "digital"

            pages.append(Page(page_number=index + 1, text=text, source=source))
    finally:
        doc.close()

    return pages


# --------------------------------------------------- running headers --------
_FOLIO_LINE = re.compile(r"^[0-9૦-૯]{1,4}$")
_GUJARATI_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")


def _folio_offset(pages: List[Page], scan: int = 2) -> Optional[int]:
    """Difference between the printed page number and the PDF page index.

    Front matter is usually unnumbered or numbered in Roman, so the printed
    folio rarely equals the index. The modal difference is the real offset;
    pages that disagree with it are not carrying a folio at all.
    """
    diffs: Dict[int, int] = {}
    for page in pages:
        lines = [ln.strip() for ln in page.text.split("\n") if ln.strip()]
        for candidate in lines[:scan] + lines[-scan:]:
            if _FOLIO_LINE.match(candidate):
                printed = int(candidate.translate(_GUJARATI_DIGITS))
                delta = page.page_number - printed
                diffs[delta] = diffs.get(delta, 0) + 1
    if not diffs:
        return None
    offset, hits = max(diffs.items(), key=lambda kv: kv[1])
    # One-off numbers (a year, a list item) are not a folio scheme.
    return offset if hits >= max(3, len(pages) // 10) else None


def strip_running_headers(pages: List[Page], threshold: float = 0.2,
                          scan: int = 2) -> List[Page]:
    """Drop the book title and folio printed at the top or bottom of each page.

    A reader's eye skips them, but they land mid-sentence in every chunk that
    spans a page break and from there into the embedding, the BM25 tokens and
    the citation snippet. Only lines repeated across many pages are removed, so
    a chapter opener — where the lone number is the chapter, not the folio —
    survives.
    """
    if len(pages) < 5:
        return pages

    counts: Dict[str, int] = {}
    for page in pages:
        lines = [ln.strip() for ln in page.text.split("\n") if ln.strip()]
        for line in set(lines[:scan] + lines[-scan:]):
            if line and not _FOLIO_LINE.match(line):
                counts[line] = counts.get(line, 0) + 1
    floor = max(3, int(len(pages) * threshold))
    repeated = {line for line, n in counts.items() if n >= floor}
    offset = _folio_offset(pages, scan)

    def is_furniture(line: str, page_number: int) -> bool:
        line = line.strip()
        if not line:
            return True
        if line in repeated:
            return True
        if offset is not None and _FOLIO_LINE.match(line):
            return int(line.translate(_GUJARATI_DIGITS)) == page_number - offset
        return False

    cleaned: List[Page] = []
    for page in pages:
        lines = page.text.split("\n")
        for _ in range(scan):
            if lines and is_furniture(lines[0], page.page_number):
                lines.pop(0)
            else:
                break
        for _ in range(scan):
            if lines and is_furniture(lines[-1], page.page_number):
                lines.pop()
            else:
                break
        cleaned.append(Page(page.page_number, "\n".join(lines).strip(), page.source))
    return cleaned


def extract_metadata(pdf_path: str | Path) -> dict:
    """Title/author/page count from the PDF's own metadata dictionary."""
    fitz = _pymupdf()

    doc = fitz.open(str(pdf_path))
    try:
        meta = doc.metadata or {}
        return {
            "title": (meta.get("title") or "").strip(),
            "author": (meta.get("author") or "").strip(),
            "page_count": doc.page_count,
        }
    finally:
        doc.close()


def extraction_stats(pages: List[Page]) -> dict:
    """Summary of how a document was read — surfaced in the upload response."""
    return {
        "total_pages": len(pages),
        "digital_pages": sum(1 for p in pages if p.source == "digital"),
        "ocr_pages": sum(1 for p in pages if p.source == "ocr"),
        "empty_pages": sum(1 for p in pages if p.source == "empty"),
        "total_characters": sum(len(p.text) for p in pages),
    }
