"""Post-generation grounding checks.

The answer prompt asks the model to quote the book and cite pages, but a
prompt is a request, not a guarantee: models silently "correct" Gujarati
spellings inside quotation marks and occasionally cite a page they were never
shown. These checks run on every generated answer, against the exact
passages the model received:

- a quoted span must match those passages exactly after `match_form`
  normalization (defined below). A quote at most MAX_QUOTE_EDITS characters
  off is replaced with the book's exact text and recorded; anything further
  off fails the answer.
- every line that states something must carry a page citation, every cited
  page must lie inside a passage the model was given, and each quote must be
  found on a page cited on its own line.
- where a line cites a passage spanning several pages, the cited pages must be
  exactly the pages whose text (rebuilt from the PDF, qa.pages) holds the
  claim. If that cannot be established, the citation is rejected.
- every number must occur in those passages, and so must every Latin-script
  word in a Gujarati answer (there, English words are names or terms taken
  from the book). Invented facts are most often a year or a name; this
  catches them even outside quotation marks. English answers are exempt
  from the word check, since ordinary English prose is not in the book.

Claims (every cited line, quoted or not) are checked in two layers:

- lexical, here in check_answer: the claim's content words are compared with
  the passages its own line cites, allowing Gujarati inflection, the book's
  one-character spelling slips and connective words. A claim that brings in
  more than MAX_NOVEL_WORDS words of its own is rejected outright.
- semantic, in verify_claims: every claim that is not an exact copy (after
  match_form) of its cited passage is judged by the LLM against those passages, with the
  claim's unmatched words listed. Faithful rewording passes; any added name,
  detail, cause or explanation, or a changed meaning, fails. No verdict counts
  as a failure.

An answer that fails is regenerated once by the graph, then not shown; the
graph falls back to "not found".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Sequence, Tuple

from indexing.bm25_index import tokenize
from qa import pages as page_source

# A quote this few characters away from a source span is the same quote with a
# transcription slip (a dropped anusvara, a changed matra); beyond it, the
# model has altered the wording, and the answer is regenerated instead.
MAX_QUOTE_EDITS = 2
# Shorter spans are words or titles, not quotations worth verifying.
MIN_QUOTE_CHARS = 8

# Double-quoted spans may contain single-quoted titles (“‘સાઈકલૉરામા’ એટલે …”),
# so they are found first and the whole span is checked; single-quoted spans
# are then taken only outside them. The plain apostrophe is never a quote mark:
# English contractions would turn into false "quotes".
_DOUBLE_QUOTE_RE = re.compile(r"“([^“”]{%d,})”|\"([^\"]{%d,})\"" % (MIN_QUOTE_CHARS, MIN_QUOTE_CHARS))
_SINGLE_QUOTE_RE = re.compile(r"‘([^‘’“”\"]{%d,})’" % MIN_QUOTE_CHARS)


def _quotes(line: str) -> List[str]:
    spans: List[str] = []
    outside = line
    for m in _DOUBLE_QUOTE_RE.finditer(line):
        spans.append(m.group(1) or m.group(2))
        outside = outside.replace(m.group(0), " ")
    return spans + _SINGLE_QUOTE_RE.findall(outside)
_ZERO_WIDTH = dict.fromkeys(map(ord, "‌‍"))
_GUJARATI_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")
# "(પાનું 201)", "(પાનાં 196-197)", "(page 42)", "(pages 12–14, 20)"
_CITATION_RE = re.compile(
    r"(?:પાનું|પાનાં|પાના|પૃષ્ઠ|pages?|p\.)\s*([0-9૦-૯][0-9૦-૯\s,\-‐‑–—]*)",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", (text or "").translate(_ZERO_WIDTH))
    return re.sub(r"\s+", " ", text).strip()


_QUOTE_MARKS = dict.fromkeys(map(ord, "“”‘’\"'«»"), "'")
_EDGE_PUNCT = " .,;:!?।|-–—'"


def match_form(text: str) -> str:
    """The only normalization applied before comparing a quote with the book:
    NFC, zero-width joiners removed, whitespace collapsed, every quotation-mark
    style mapped to one, punctuation trimmed from both ends, and English words
    rejoined where the PDF hyphenated them across a line break. Letters,
    vowel signs and word order are never altered."""
    text = normalize(text).translate(_QUOTE_MARKS)
    text = re.sub(r"([A-Za-z])-\s+([a-z])", r"\1\2", text)
    return text.strip(_EDGE_PUNCT)


def _edits(a: str, b: str) -> int:
    """Characters inserted, deleted or replaced to turn `a` into `b`."""
    ops = SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in ops if tag != "equal")


@dataclass
class GroundingResult:
    answer: str
    snapped: List[Tuple[str, str]] = field(default_factory=list)  # (model's, book's)
    problems: List[str] = field(default_factory=list)
    pages_moved: List[Tuple[str, str]] = field(default_factory=list)  # (cited, corrected)

    @property
    def ok(self) -> bool:
        return not self.problems


def _closest_span(quote: str, source: str) -> Tuple[float, str]:
    """Best-matching substring of `source` for `quote`, allowing small length drift."""
    best_ratio, best_span = 0.0, ""
    n = len(quote)
    matcher = SequenceMatcher(autojunk=False)
    matcher.set_seq2(quote)
    for length in range(max(1, n - 3), n + 4):
        for start in range(0, max(0, len(source) - length) + 1):
            window = source[start:start + length]
            matcher.set_seq1(window)
            if matcher.real_quick_ratio() < best_ratio or matcher.quick_ratio() < best_ratio:
                continue
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio, best_span = ratio, window
    return best_ratio, best_span.strip()


def _cited_pages(answer: str) -> List[int]:
    pages: List[int] = []
    for match in _CITATION_RE.finditer(answer):
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1).translate(_GUJARATI_DIGITS))]
        if re.search(r"\d\s*[\-‐‑–—]\s*\d", match.group(1)) and len(numbers) == 2:
            pages.extend(range(numbers[0], numbers[1] + 1))
        else:
            pages.extend(numbers)
    return pages


_NUMBER_RE = re.compile(r"[0-9૦-૯]+")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]{2,}")
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]\s*)?[0-9૦-૯]+[.)]\s", re.MULTILINE)
# Formatting words a model may add that are not claims about the book.
_LATIN_ALLOWED = {"page", "pages", "chapter"}


def _unsupported_tokens(answer: str, chunks: Sequence) -> List[str]:
    """Numbers and Latin-script words in the answer that no passage contains."""
    body = _CITATION_RE.sub(" ", answer)
    body = _LIST_MARKER_RE.sub(" ", body)
    corpus = " ".join(normalize(f"{c.chapter_title} {c.text}") for c in chunks)
    # PDF line breaks hyphenate English words: "command- ing image".
    corpus = re.sub(r"([A-Za-z])-\s+([a-z])", r"\1\2", corpus)
    numbers = {n.translate(_GUJARATI_DIGITS) for n in _NUMBER_RE.findall(corpus)}
    lowered = corpus.lower()

    missing: List[str] = []
    for n in _NUMBER_RE.findall(body):
        if n.translate(_GUJARATI_DIGITS) not in numbers:
            missing.append(n)
    gujarati = len(re.findall(r"[\u0A80-\u0AFF]", body))
    if gujarati <= len(re.findall(r"[A-Za-z]", body)):
        return missing
    for word in _LATIN_WORD_RE.findall(body):
        w = word.lower().strip("'’-")
        if w not in _LATIN_ALLOWED and w not in lowered:
            missing.append(word)
    return missing


def _pages(c) -> set:
    return set(range(c.page_start, c.page_end + 1))


def _check_quote(raw: str, line_pages: set, chunks: Sequence, result: GroundingResult) -> None:
    quote = match_form(raw)
    forms = [(c, match_form(c.text)) for c in chunks]
    holders = [c for c, text in forms if quote in text]
    if not holders:
        best = max(((_closest_span(quote, text), c) for c, text in forms),
                   key=lambda x: x[0][0], default=None)
        span = best[0][1].strip(_EDGE_PUNCT) if best else ""
        if not span or _edits(quote, span) > MAX_QUOTE_EDITS:
            result.problems.append(f"quote not in passages: {quote[:80]}")
            return
        result.answer = result.answer.replace(raw, span)
        result.snapped.append((quote, span))
        holders = [best[1]]
    if line_pages and not any(_pages(c) & line_pages for c in holders):
        found_on = sorted(set().union(*(_pages(c) for c in holders)))
        result.problems.append(f"quote is on pages {found_on}, not the cited {sorted(line_pages)}: "
                               f"{quote[:60]}")


def check_answer(answer: str, chunks: Sequence) -> GroundingResult:
    """Verify citations, quotes, numbers and Latin-script names in `answer`."""
    result = GroundingResult(answer=answer)
    shown = set().union(*(_pages(c) for c in chunks)) if chunks else set()

    for line in answer.splitlines():
        content = _CITATION_RE.sub(" ", line)
        if not re.search(r"[A-Za-z\u0A80-\u0AFF]", content) or line.rstrip().endswith(":"):
            continue  # blank, punctuation-only, or an introductory "…:" line
        line_pages = set(_cited_pages(line))
        if not line_pages:
            result.problems.append(f"no page citation: {normalize(line)[:60]}")
        for page in sorted(line_pages - shown):
            result.problems.append(f"cites page {page}, not among passages {sorted(shown)}")
        for raw in _quotes(line):
            _check_quote(raw, line_pages, chunks, result)

    for token in _unsupported_tokens(answer, chunks):
        result.problems.append(f"not in passages: {token}")

    for claim in extract_claims(result.answer, chunks):
        if not claim.passages:
            result.problems.append(f"claim cites no passage shown: {claim.text[:60]}")
        elif len(claim.novel) > MAX_NOVEL_WORDS:
            result.problems.append(
                f"claim adds words not in its cited passages ({', '.join(claim.novel)}): "
                f"{claim.text[:60]}")

    result.problems.extend(page_problems(result.answer, chunks))
    return result


# --------------------------------------------------------------- claims ----
# A claim may reword its passage, so a couple of its words need not appear
# there; those go to the semantic check. More than this, and the claim is
# bringing its own content (the elaboration and invented-name failures).
MAX_NOVEL_WORDS = 2

# Inflections a Gujarati word takes in a sentence; stripped before matching so
# "નટોની" in an answer matches "નટોનો" in the book. Longest first.
_SUFFIXES = sorted([
    "ઓનો", "ઓની", "ઓના", "ઓનું", "ઓનાં", "ઓમાં", "ઓથી", "ઓને", "ઓએ",
    "નો", "ની", "ના", "નું", "નાં", "માં", "થી", "ને", "એ", "ે", "ો", "ી", "ું", "ા", "ં",
], key=len, reverse=True)

# Connective and auxiliary words a faithful paraphrase needs that carry no
# claim of their own. Content words (nouns, names, qualities) are never here.
_GLUE = {
    "એટલે", "કે", "જે", "જેને", "જેમાં", "તેને", "તેમાં", "તેનો", "તેની", "તેના", "તેનું",
    "આવે", "આવતો", "આવતી", "આવતું", "આવતા", "આવ્યો", "આવ્યું", "આવી", "આવ્યા",
    "થાય", "થયું", "થઈ", "થયો", "થયા", "હોય", "હતું", "હોવો", "હોવી", "હોવું",
    "કરે", "કરી", "કર્યું", "કરવામાં", "કરવું", "કરવો", "કરવા", "કરાય", "રાખવામાં",
    "થતાં", "થતા", "ત્યારે",
    "દ્વારા", "તરીકે", "રીતે", "મુજબ", "અનુસાર", "કહેવાય", "કહે", "કહેવામાં", "શકાય",
    "પુસ્તક", "પુસ્તકમાં", "પુસ્તકના", "પુસ્તકની", "ઉત્તર", "ફકરા", "ફકરામાં",
}


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            return word[: -len(suffix)]
    return word


def _word_supported(word: str, text: str, words: Iterable[str]) -> bool:
    if word in _GLUE or word.isdigit():
        return True
    stem = _stem(word)
    if len(stem) >= 3 and stem in text:
        return True  # also covers forms glued to quote marks: ‘કાબૂકી’માં
    if word in words or (len(word) >= 3 and any(w.startswith(word) for w in words)):
        return True  # "નટો" in the answer, "નટોનો" in the book
    # The PDF's text layer often drops a virama or a vowel sign (સટેજ for
    # સ્ટેજ); one character's difference on a word of four or more is the
    # same word.
    return len(stem) >= 4 and any(abs(len(w) - len(stem)) <= 1 and _edits(stem, w) <= 1
                                  for w in map(_stem, words))


@dataclass
class Claim:
    text: str                 # the line, citations removed
    pages: set
    passages: list            # chunks whose pages the line cites
    novel: List[str]          # content words not found in those passages
    verbatim: bool            # exact copy (after match_form) of a span of a passage
    quotes: List[str] = field(default_factory=list)  # quoted spans on the line


# A bracketed group holding a citation, e.g. "(પાનું 15, પ્રકરણ 1)": removed
# whole. Other brackets belong to the claim and to the book's own text.
_CITED_GROUP_RE = re.compile(
    r"[(\[][^()\[\]]*?(?:પાનું|પાનાં|પાના|પૃષ્ઠ|pages?|p\.)[^()\[\]]*[)\]]", re.IGNORECASE)


def _strip_citations(line: str) -> str:
    return _CITATION_RE.sub(" ", _CITED_GROUP_RE.sub(" ", line))


def _is_gujarati(text: str) -> bool:
    return len(re.findall(r"[\u0A80-\u0AFF]", text)) > len(re.findall(r"[A-Za-z]", text))


def extract_claims(answer: str, chunks: Sequence) -> List[Claim]:
    """One claim per cited line (blank and introductory "…:" lines skipped)."""
    claims: List[Claim] = []
    for line in answer.splitlines():
        body = _LIST_MARKER_RE.sub(" ", _strip_citations(line))
        if not re.search(r"[A-Za-z\u0A80-\u0AFF]", body) or line.rstrip().endswith(":"):
            continue
        pages = set(_cited_pages(line))
        passages = [c for c in chunks if _pages(c) & pages]
        text = match_form(body)
        plain = text.replace("'", "")
        verbatim = False
        novel: List[str] = []
        if passages:
            forms = [match_form(c.text).replace("'", "") for c in passages]
            # Only an exact copy skips the semantic check: a single inserted
            # "ન" or a changed letter can reverse the meaning.
            verbatim = bool(plain) and any(plain in f for f in forms)
            if _is_gujarati(body) and not verbatim:
                joined = " ".join(forms)
                lowered = joined.lower()
                words = set(tokenize(joined))
                novel = [w for w in dict.fromkeys(tokenize(body))
                         if not _word_supported(w, lowered, words)]
        quotes = [match_form(q).replace("'", "") for q in _quotes(line)]
        claims.append(Claim(text, pages, passages, novel, verbatim, quotes))
    return claims


# ---------------------------------------------------------- exact pages ----
# Share of a paraphrase's content words a page must hold to count as the page
# the claim comes from.
PAGE_SUPPORT_MIN = 0.6


def _flat(text: str) -> str:
    return match_form(text).replace("'", "")


def _span_pages(needle: str, forms: dict) -> set:
    """Pages holding `needle`, including a sentence that runs across a break."""
    hits = {p for p, t in forms.items() if needle in t}
    if hits:
        return hits
    ordered = sorted(forms)
    for a, b in zip(ordered, ordered[1:]):
        if b != a + 1:
            continue
        for k in range(8, len(needle) - 7):  # both halves at least 8 characters
            head, tail = needle[:k].strip(), needle[k:].strip()
            if head and tail and head in forms[a] and tail in forms[b]:
                return {a, b}
    return set()


def _overlap_pages(claim_text: str, forms: dict) -> set:
    words = [w for w in dict.fromkeys(tokenize(claim_text)) if w not in _GLUE and not w.isdigit()]
    if not words:
        return set()
    found = set()
    for page, text in forms.items():
        lowered, page_words = text.lower(), set(tokenize(text))
        share = sum(_word_supported(w, lowered, page_words) for w in words) / len(words)
        if share >= PAGE_SUPPORT_MIN:
            found.add(page)
    return found


def locate_pages(claim: Claim, chunk) -> Optional[set]:
    """The exact pages of a multi-page `chunk` that state `claim`.

    None if any page's text is unreadable. An empty set if the claim cannot
    be placed: an English paraphrase without a quote, or Gujarati wording
    too far from every page.
    """
    doc_id = page_source.doc_id_of(chunk)
    texts = {p: page_source.page_text(doc_id, p) for p in range(chunk.page_start, chunk.page_end + 1)}
    if any(t is None for t in texts.values()):
        return None
    forms = {p: _flat(t) for p, t in texts.items()}
    chunk_form = _flat(chunk.text)
    needles = [q for q in claim.quotes if q and q in chunk_form]
    if claim.verbatim:
        needles.append(_flat(claim.text))
    if needles:
        located = set()
        for needle in needles:
            located |= _span_pages(needle, forms)
        return located
    if _is_gujarati(claim.text):
        return _overlap_pages(claim.text, forms)
    return set()


def page_problems(answer: str, chunks: Sequence) -> List[str]:
    problems: List[str] = []
    for claim in extract_claims(answer, chunks):
        for chunk in claim.passages:
            if chunk.page_end <= chunk.page_start:
                continue  # a one-page passage pins the page exactly
            span = _pages(chunk)
            cited = claim.pages & span
            located = locate_pages(claim, chunk)
            where = f"pages {chunk.page_start}-{chunk.page_end}"
            if located is None:
                problems.append(f"cannot read {where} to confirm the cited page: {claim.text[:50]}")
            elif not located:
                problems.append(f"cannot establish which of {where} states this; quote the "
                                f"passage and cite its exact page: {claim.text[:50]}")
            elif cited != located:
                problems.append(f"cites page(s) {sorted(cited)}, but this is on page(s) "
                                f"{sorted(located)}: {claim.text[:50]}")
    return problems


def _page_label(pages: Sequence[int], gujarati: bool) -> str:
    pages = sorted(pages)
    if len(pages) == 1:
        return f"{'પાનું' if gujarati else 'page'} {pages[0]}"
    run = pages == list(range(pages[0], pages[-1] + 1))
    numbers = f"{pages[0]}-{pages[-1]}" if run else ", ".join(map(str, pages))
    return f"{'પાનાં' if gujarati else 'pages'} {numbers}"


def snap_citations(answer: str, chunks: Sequence) -> Tuple[str, List[Tuple[str, str]]]:
    """Rewrite a line's page citation to the pages that actually hold its claim.

    page_problems rejects a citation of a multi-page passage unless it names
    exactly the pages whose text states the claim. When those pages can be
    established, the citation is moved there instead, the way a misspelt
    quote is snapped to the book's text. Only lines with a single citation
    are touched, and only when every cited passage could be read and placed;
    the answer must still pass check_answer afterwards.

    Returns (answer, [(old citation, new citation), ...]).
    """
    lines = answer.split("\n")
    moved: List[Tuple[str, str]] = []
    for k, line in enumerate(lines):
        matches = list(_CITATION_RE.finditer(line))
        claims = extract_claims(line, chunks)
        if len(matches) != 1 or len(claims) != 1 or not claims[0].passages:
            continue
        claim = claims[0]
        located: set = set()
        for chunk in claim.passages:
            if chunk.page_end <= chunk.page_start:
                located |= _pages(chunk) & claim.pages
                continue
            found = locate_pages(claim, chunk)
            if not found:
                located = set()
                break
            located |= found
        if not located or located == claim.pages:
            continue
        m = matches[0]
        old = m.group(0).rstrip(" ,;")
        new = _page_label(located, _is_gujarati(line))
        lines[k] = line[:m.start()] + new + line[m.start() + len(old):]
        moved.append((old, new))
    return "\n".join(lines), moved


def verify_claims(answer: str, chunks: Sequence, llm) -> Tuple[List[str], int]:
    """Semantic check of every claim that is not a near-verbatim copy.

    Returns (problems, claims_sent_to_the_llm). Raises LLMError if the
    verifier cannot be reached: an unverifiable answer is never shown.
    """
    from qa import prompt_builder  # avoid an import cycle at module load

    pending = [c for c in extract_claims(answer, chunks) if c.passages and not c.verbatim]
    if not pending:
        return [], 0
    payload = llm.generate_json(prompt_builder.build_claim_check_prompt(pending),
                                system=prompt_builder.CLAIM_CHECK_SYSTEM, temperature=0.0)
    verdicts = payload.get("claims", []) if isinstance(payload, dict) else payload
    supported = {}
    for v in verdicts or []:
        if isinstance(v, dict):
            try:
                supported[int(v.get("claim", 0))] = (v.get("supported") is True,
                                                     str(v.get("reason", ""))[:120])
            except (TypeError, ValueError):
                continue
    problems = []
    for i, claim in enumerate(pending, start=1):
        ok, reason = supported.get(i, (False, "no verdict returned"))
        if not ok:
            problems.append(f"claim not supported by its cited passages ({reason}): {claim.text[:60]}")
    return problems, len(pending)
