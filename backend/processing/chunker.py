"""Structure-aware chunking for Gujarati books.

Two things make this different from a naive character splitter:

1.  Sentence boundaries follow Gujarati punctuation. Gujarati prose ends
    sentences with the danda (।), not a full stop, so a splitter tuned for
    English cuts mid-sentence on nearly every line.
2.  Chunks never cross a chapter boundary, and every chunk carries the page
    range and chapter it came from. That metadata is what makes a citation
    like "page 42, પ્રકરણ ૩" possible at answer time.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Sequence

import config
from processing.pdf_extractor import Page

logger = logging.getLogger(__name__)


# ------------------------------------------------------------- dataclasses --
@dataclass
class Chapter:
    index: int              # 0-based position in the book
    title: str
    start_page: int
    end_page: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    chapter_index: int      # -1 when the book has no detectable chapters
    chapter_title: str
    token_count: int

    def to_dict(self) -> dict:
        return asdict(self)

    def metadata(self) -> dict:
        """The subset stored alongside the vector in ChromaDB."""
        return {
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chapter_index": self.chapter_index,
            "chapter_title": self.chapter_title,
            "token_count": self.token_count,
        }


# ---------------------------------------------------------- token counting --
_hf_tokenizer = None
_hf_tokenizer_tried = False
_GUJARATI_RANGE = re.compile(r"[઀-૿]")


def _load_hf_tokenizer():
    """Lazily load the embedding model's own tokenizer.

    Counting with the real tokenizer means a 400-token chunk is genuinely 400
    tokens to multilingual-e5-base. If transformers or the model cache is not
    available (offline first run), fall back to the heuristic below.
    """
    global _hf_tokenizer, _hf_tokenizer_tried
    if _hf_tokenizer_tried:
        return _hf_tokenizer
    _hf_tokenizer_tried = True
    try:
        from transformers import AutoTokenizer
        _hf_tokenizer = AutoTokenizer.from_pretrained(config.EMBEDDING_MODEL)
    except Exception as exc:
        logger.warning("Exact tokenizer unavailable (%s); using estimate.", exc)
        _hf_tokenizer = None
    return _hf_tokenizer


def _estimate_tokens(text: str) -> int:
    """Rough token count for when the real tokenizer cannot be loaded.

    XLM-R's sentencepiece vocabulary splits Gujarati words into roughly 2-3
    pieces, against ~1.3 for Latin words, so the two scripts are weighted
    separately.
    """
    words = text.split()
    if not words:
        return 0
    gujarati = sum(1 for w in words if _GUJARATI_RANGE.search(w))
    latin = len(words) - gujarati
    return int(gujarati * 2.4 + latin * 1.3) + 1


def count_tokens(text: str) -> int:
    tok = _load_hf_tokenizer()
    if tok is None:
        return _estimate_tokens(text)
    return len(tok.encode(text, add_special_tokens=False))


# -------------------------------------------------------- chapter detection --
_GUJARATI_NUMBER_WORDS = (
    "એક|બે|ત્રણ|ચાર|પાંચ|છ|સાત|આઠ|નવ|દસ|અગિયાર|બાર|તેર|ચૌદ|પંદર|સોળ|સત્તર|"
    "અઢાર|ઓગણીસ|વીસ|એકવીસ|બાવીસ|ત્રેવીસ|ચોવીસ|પચીસ"
)
# પ્રકરણ ૩ / અધ્યાય 3 / ખંડ-૨ / Chapter 3 / પ્રકરણ ત્રણ
_CHAPTER_PATTERN = re.compile(
    r"^\s*(?:(પ્રકરણ|અધ્યાય|ખંડ|ભાગ|પરિચ્છેદ)|(?i:chapter|section|part))"
    r"\s*[-–—:.]?\s*"
    r"(?:([0-9૦-૯]{1,3})|(" + _GUJARATI_NUMBER_WORDS + r")|([IVXLC]{1,6}\b))"
    r"\s*[-–—:.]?\s*(.{0,60})$"
)
# A numbered heading: "૩. વિદાય", "3) Departure", "5 નાટકના પ્રકારો".
# The optional second number distinguishes a chapter ("4. શીર્ષક") from a
# section inside one ("4.6 શીર્ષક"), which must not become a chapter of its own.
_NUMBERED_HEADING = re.compile(
    r"^\s*([0-9૦-૯]{1,2})(?:\s*[.\-–]\s*([0-9૦-૯]{1,2}))?\s*[.):]?\s+(\S.{0,58})$"
)
# A typeset book often prints the chapter number alone on one line and the
# title on the next, with no "પ્રકરણ" anywhere on the page.
_BARE_NUMBER = re.compile(r"^\s*([0-9૦-૯]{1,2})\s*[.)]?\s*$")
# Front matter that lists every heading in the book. Those pages have to be
# skipped wholesale or each listed line becomes a chapter start.
_CONTENTS_TITLE = re.compile(
    r"^\s*(અનુક્રમ|અનુક્રમણિકા|વિષયસૂચિ|વિષયાનુક્રમ|સૂચિ|તસવીરોની\s+વિગત"
    r"|contents?|index|table\s+of\s+contents)\s*$",
    re.IGNORECASE,
)
# A line that continues into prose is not a heading: "9. નટની મનોદશા. નટે..."
_SENTENCE_BREAK = re.compile(r"[।.]\s+\S")

_MAX_HEADING_CHARS = 80
_GUJARATI_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")


def _to_int(text: str) -> Optional[int]:
    try:
        return int(text.translate(_GUJARATI_DIGITS))
    except (ValueError, AttributeError):
        return None


def _plausible_title(text: str) -> bool:
    """Is this short line a heading, rather than a sentence or a page number?"""
    if not text or len(text) > _MAX_HEADING_CHARS:
        return False
    if _SENTENCE_BREAK.search(text) or len(text.split()) > 12:
        return False
    # A real title contains letters and does not open with a number: a caption
    # like "5. 3/4 પીઠ દર્શાવતી સ્થિતિ" is numbered twice, a chapter once.
    if text[0].isdigit() or text[0] in "૦૧૨૩૪૫૬૭૮૯":
        return False
    # OCR noise such as "- ૨" carries no letters at all.
    if not re.search(r"[^\W\d_]", text) or _BARE_NUMBER.match(text):
        return False
    # OCR noise such as 'a હિ "' mixes stray symbols and lone Latin letters
    # into Gujarati; a real title has none.
    gujarati = bool(_GUJARATI_RANGE.search(text))
    for word in text.split():
        if word in "-–—:":
            continue
        if not any(ch.isalpha() or _GUJARATI_RANGE.match(ch) for ch in word):
            return False
        if gujarati and re.fullmatch(r"[A-Za-z]", word):
            return False
    return True


def _parse_heading(line: str) -> Optional[tuple]:
    """(level, number, title) for a heading line, else None.

    level 1 is a chapter, level 2 a section inside one. `number` is None for
    headings numbered with words or Roman numerals.
    """
    stripped = re.sub(r"\s+", " ", line.strip())
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return None
    # A heading is a short standalone line, never a sentence. The sentence
    # check belongs on the title alone: applied to the whole line it trips on
    # the heading's own numbering — "1. નાટક" and the spaced separator OCR
    # produces for "પ્રકરણ ૩ . વળતર" both look like a full stop mid-line.
    if stripped.endswith(("।", ".", "?", "!", ",", ";")) and len(stripped.split()) > 6:
        return None

    m = _CHAPTER_PATTERN.match(stripped)
    if m:
        return (1, _to_int(m.group(2)) if m.group(2) else None, stripped)

    m = _NUMBERED_HEADING.match(stripped)
    if m and len(stripped.split()) <= 10 and _plausible_title(m.group(3)):
        level = 2 if m.group(2) else 1
        return (level, _to_int(m.group(1)), stripped)
    return None


def _running_headers(pages: Sequence[Page], threshold: float = 0.2) -> set:
    """Lines that top most pages — the book title printed on every page.

    Without this the running header pairs up with the folio above it and every
    page looks like the start of a new chapter.
    """
    counts: Dict[str, int] = {}
    for page in pages:
        lines = [ln.strip() for ln in page.text.split("\n") if ln.strip()][:3]
        for line in set(lines):
            counts[line] = counts.get(line, 0) + 1
    floor = max(3, int(len(pages) * threshold))
    return {line for line, n in counts.items() if n >= floor}


def _page_candidates(page: Page, headers: set) -> List[tuple]:
    """Every heading-looking line on a page, as (level, number, title)."""
    lines = [ln.strip() for ln in page.text.split("\n") if ln.strip()]
    found: List[tuple] = []
    for i, line in enumerate(lines):
        if line in headers:
            continue
        parsed = _parse_heading(line)
        if parsed:
            found.append(parsed)
            continue
        # "1" on its own line, the title on the next: a chapter opener, unless
        # the number is just this page's folio.
        m = _BARE_NUMBER.match(line)
        if m and i + 1 < len(lines):
            number = _to_int(m.group(1))
            title = lines[i + 1]
            if (number is not None and number != page.page_number
                    and title not in headers and _plausible_title(title)):
                found.append((1, number, f"{number}. {title}"))
    return found


# An anthology or textbook opens each piece with its title and then the
# author on a line of its own: "આ તો ઈશ તણો આવાસ" / "- કરસનદાસ માણેક".
_BYLINE = re.compile(r"^\s*[-–—]\s*[“\"'‘]?(\S[^.?!।]{1,40}?)[”\"'’]?\s*$")
_BYLINE_SCAN_LINES = 4
# Minimum anthology openers before they are trusted over numbered headings.
_MIN_BYLINE_CHAPTERS = 3


def _byline_name(line: str) -> Optional[str]:
    m = _BYLINE.match(line)
    if not m:
        return None
    name = m.group(1).strip(" “”\"'‘’")
    words = name.split()
    if not 1 <= len(words) <= 4 or not _GUJARATI_RANGE.search(name):
        return None
    return name


def _usable_title(line: str) -> bool:
    """A title line OCR read cleanly enough to show (decorative fonts often fail)."""
    # Vowel signs and the virama are not isalpha(); count the whole script.
    letters = sum(1 for ch in line if ch.isalpha() or _GUJARATI_RANGE.match(ch))
    return (len(_GUJARATI_RANGE.findall(line)) >= 4 and letters >= 0.6 * len(line.replace(" ", ""))
            and len(line) <= 60)


def _byline_opener(page: Page) -> Optional[tuple]:
    """(title, title_is_real) for the piece that starts on this page, if one does.

    Accepted when the author line near the top is either followed by the
    author's biography (which opens with their name) or is the only author
    line on the page beneath a title. That rejects epigraph pages, which
    stack several quoted verses each with its poet, and dialogue lines that
    happen to start with a dash. A title too garbled to show falls back to
    the author's name (title_is_real False).
    """
    lines = [ln.strip() for ln in page.text.split("\n") if ln.strip()]
    bylines = [i for i, ln in enumerate(lines) if _byline_name(ln)]
    for i in bylines:
        if i >= _BYLINE_SCAN_LINES:
            break
        name = _byline_name(lines[i])
        title = lines[i - 1] if i > 0 else ""
        has_title = bool(title) and _usable_title(title)
        bio = " ".join(lines[i + 1:i + 5])
        if name.split()[0] in bio or (has_title and len(bylines) == 1):
            return (title, True) if has_title else (name, False)
    return None


def _byline_chapters(pages: Sequence[Page]) -> List[tuple]:
    """(page_number, title, title_is_real) for every piece opener."""
    found = []
    for page in pages:
        opener = _byline_opener(page) if page.text else None
        if opener:
            found.append((page.page_number, *opener))
    return found


# "ગઢની રઢ છોડો ! 14", "માંડી અમારી વાત... 122": a contents line ends in the
# printed page number.
_TOC_ENTRY = re.compile(r"^(.*?\S)[\s.…·]*\s([0-9૦-૯]{1,3})$")
_TOC_KEY = re.compile(r"[\W_]+")


def _toc_entries(pages: Sequence[Page]) -> List[tuple]:
    """(printed_page, title) for each readable line of the contents pages."""
    entries = []
    for page in pages:
        lines = [ln.strip() for ln in page.text.split("\n") if ln.strip()]
        if not lines or not _CONTENTS_TITLE.match(lines[0]):
            continue
        for line in lines[1:]:
            m = _TOC_ENTRY.match(line)
            if m and _usable_title(m.group(1)):
                entries.append((_to_int(m.group(2)), m.group(1).strip()))
    return entries


def _same_title(a: str, b: str) -> bool:
    ka, kb = _TOC_KEY.sub("", a), _TOC_KEY.sub("", b)
    return bool(ka) and bool(kb) and (ka in kb or kb in ka)


def _apply_contents(openers: List[tuple], pages: Sequence[Page]) -> List[tuple]:
    """Use the book's contents page to name and complete the piece openers.

    The printed page numbers are offset from PDF pages by the front matter;
    the offset is taken from contents entries whose titles were also read on
    the page itself, and is trusted only when two or more agree. Then a
    contents title replaces an author-name placeholder, and a listed piece
    whose opener OCR missed entirely is added, unless a detected opener sits
    within a page of it (a misread page number).
    """
    entries = _toc_entries(pages)
    votes: Dict[int, int] = {}
    for start, title, real in openers:
        for printed, toc_title in entries:
            if real and _same_title(title, toc_title):
                votes[start - printed] = votes.get(start - printed, 0) + 1
    if not votes:
        return openers
    offset, agreeing = max(votes.items(), key=lambda kv: kv[1])
    if agreeing < 2:
        return openers

    by_page = {start: (title, real) for start, title, real in openers}
    first, last = pages[0].page_number, pages[-1].page_number
    for printed, toc_title in entries:
        target = printed + offset
        if not first <= target <= last:
            continue
        if target in by_page:
            if not by_page[target][1]:
                by_page[target] = (toc_title, True)
        elif not any(abs(target - start) <= 1 for start in by_page):
            by_page[target] = (toc_title, True)
    return [(start, *by_page[start]) for start in sorted(by_page)]


def _to_chapters(kept: Sequence[tuple], pages: Sequence[Page]) -> List[Chapter]:
    last_page = pages[-1].page_number if pages else 0
    chapters: List[Chapter] = []
    for i, (start_page, title) in enumerate(kept):
        end_page = kept[i + 1][0] - 1 if i + 1 < len(kept) else last_page
        chapters.append(
            Chapter(index=i, title=title, start_page=start_page, end_page=max(end_page, start_page))
        )
    return chapters


def detect_chapters(pages: Sequence[Page]) -> List[Chapter]:
    """Scan the book for chapter headings and turn them into page ranges.

    Only the first few lines of each page are considered: in a typeset book a
    chapter heading starts a page, while the same words appearing mid-page are
    almost always a cross-reference ("જેમ પ્રકરણ ૨ માં જોયું...").

    A book whose pieces open with title + author line (anthologies, school
    textbooks) is split on those; numbered exercise lines inside such a book
    would otherwise pass for chapter headings.
    """
    openers = _byline_chapters(pages)
    if len(openers) >= _MIN_BYLINE_CHAPTERS:
        openers = _apply_contents(openers, pages)
        return _to_chapters([(start, title) for start, title, _ in openers], pages)
    # Too few openers to outrank numbered headings, but better than nothing
    # (an excerpt holding one or two pieces).
    return _numbered_chapters(pages) or _to_chapters([(s, t) for s, t, _ in openers], pages)


def _numbered_chapters(pages: Sequence[Page]) -> List[Chapter]:
    headers = _running_headers(pages)

    found: List[tuple] = []  # (page_number, level, number, title)
    for page in pages:
        if not page.text:
            continue
        lines = [ln for ln in page.text.split("\n") if ln.strip()]
        if lines and _CONTENTS_TITLE.match(lines[0].strip()):
            continue
        # A page carrying several headings is a table of contents or a list of
        # illustrations, not the start of a chapter.
        if len(_page_candidates(page, headers)) >= 3:
            continue
        head = Page(page.page_number, "\n".join(lines[:6]), page.source)
        for level, number, title in _page_candidates(head, headers):
            found.append((page.page_number, level, number, title))
            break  # at most one chapter starts per page

    # Sections ("4.6 ...") are only chapters in a book that has no real ones.
    if any(level == 1 for _, level, _, _ in found):
        found = [f for f in found if f[1] == 1]

    # Chapter numbers run upward. Anything that goes backwards is a heading
    # from a cross-reference, a stray list or the book's own numbering slips.
    kept: List[tuple] = []
    highest = 0
    for page_number, level, number, title in found:
        if number is not None:
            if number <= highest:
                continue
            highest = number
        kept.append((page_number, title))

    if not kept:
        return []

    chapters = _to_chapters(kept, pages)

    # A "chapter" every other page is heading noise, not structure.
    if len(pages) and len(chapters) > max(3, len(pages) // 3):
        logger.info("Chapter detection found %d candidates in %d pages; treating as noise.",
                    len(chapters), len(pages))
        return []
    return chapters


def chapter_for_page(chapters: Sequence[Chapter], page_number: int) -> Optional[Chapter]:
    for ch in chapters:
        if ch.start_page <= page_number <= ch.end_page:
            return ch
    return None


# ------------------------------------------------------- sentence splitting --
# Split after Gujarati danda / double danda, or after Latin terminal
# punctuation, when followed by whitespace.
_SENTENCE_END = re.compile(r"(?<=[।॥?!])\s+|(?<=[.])\s+(?=[^\s])")


def split_sentences(text: str) -> List[str]:
    """Split Gujarati (and mixed) prose into sentences.

    Paragraph breaks are treated as hard boundaries so a chunk never silently
    glues two paragraphs into one run-on sentence.
    """
    sentences: List[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for part in _SENTENCE_END.split(paragraph):
            part = part.strip()
            if part:
                sentences.append(part)
    return sentences


# ---------------------------------------------------------------- chunking --
@dataclass
class _Unit:
    """One sentence, tagged with the page it was read from."""
    text: str
    page: int
    tokens: int


def _page_units(pages: Sequence[Page], first: int, last: int) -> List[_Unit]:
    units: List[_Unit] = []
    for page in pages:
        if not (first <= page.page_number <= last) or not page.text:
            continue
        for sentence in split_sentences(page.text):
            units.append(_Unit(sentence, page.page_number, count_tokens(sentence)))
    return units


def _split_long_unit(unit: _Unit, limit: int) -> List[_Unit]:
    """Break a sentence that is longer than a whole chunk on word boundaries."""
    words = unit.text.split()
    out: List[_Unit] = []
    buf: List[str] = []
    for word in words:
        buf.append(word)
        if count_tokens(" ".join(buf)) >= limit:
            joined = " ".join(buf)
            out.append(_Unit(joined, unit.page, count_tokens(joined)))
            buf = []
    if buf:
        joined = " ".join(buf)
        out.append(_Unit(joined, unit.page, count_tokens(joined)))
    return out or [unit]


def _pack(units: Sequence[_Unit], size: int, overlap: int) -> List[List[_Unit]]:
    """Greedily pack sentences into ~`size`-token windows with `overlap` carry."""
    windows: List[List[_Unit]] = []
    current: List[_Unit] = []
    current_tokens = 0

    for unit in units:
        pieces = [unit] if unit.tokens <= size else _split_long_unit(unit, size)
        for piece in pieces:
            if current and current_tokens + piece.tokens > size:
                windows.append(current)
                # Carry the tail of the finished window into the next one so a
                # fact split across the boundary is retrievable from both.
                carry: List[_Unit] = []
                carried = 0
                for prev in reversed(current):
                    if carried + prev.tokens > overlap:
                        break
                    carry.insert(0, prev)
                    carried += prev.tokens
                current = list(carry)
                current_tokens = carried
            current.append(piece)
            current_tokens += piece.tokens

    if current:
        windows.append(current)
    return windows


def chunk_document(
    doc_id: str,
    pages: Sequence[Page],
    chapters: Optional[Sequence[Chapter]] = None,
    chunk_size: int = None,
    overlap: int = None,
) -> List[Chunk]:
    """Turn extracted pages into citation-carrying chunks.

    Chunks are built per chapter so that no chunk — and therefore no citation —
    straddles two chapters. Books with no detectable chapters are chunked as a
    single span with chapter_index -1.
    """
    chunk_size = chunk_size or config.CHUNK_SIZE_TOKENS
    overlap = overlap if overlap is not None else config.CHUNK_OVERLAP_TOKENS
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    if chapters is None:
        chapters = detect_chapters(pages)

    if chapters:
        spans = [(c.index, c.title, c.start_page, c.end_page) for c in chapters]
        # Front matter before the first chapter still needs indexing.
        first_start = chapters[0].start_page
        if pages and pages[0].page_number < first_start:
            spans.insert(0, (-1, "", pages[0].page_number, first_start - 1))
    else:
        spans = [(-1, "", pages[0].page_number if pages else 1,
                  pages[-1].page_number if pages else 1)]

    chunks: List[Chunk] = []
    for chapter_index, chapter_title, start_page, end_page in spans:
        units = _page_units(pages, start_page, end_page)
        if not units:
            continue
        for window in _pack(units, chunk_size, overlap):
            text = " ".join(u.text for u in window).strip()
            if not text:
                continue
            idx = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{idx}",
                    doc_id=doc_id,
                    chunk_index=idx,
                    text=text,
                    page_start=min(u.page for u in window),
                    page_end=max(u.page for u in window),
                    chapter_index=chapter_index,
                    chapter_title=chapter_title,
                    token_count=sum(u.tokens for u in window),
                )
            )
    return chunks


def chunking_stats(chunks: Sequence[Chunk]) -> dict:
    if not chunks:
        return {"chunk_count": 0, "avg_tokens": 0, "min_tokens": 0, "max_tokens": 0}
    counts = [c.token_count for c in chunks]
    return {
        "chunk_count": len(chunks),
        "avg_tokens": round(sum(counts) / len(counts), 1),
        "min_tokens": min(counts),
        "max_tokens": max(counts),
    }
