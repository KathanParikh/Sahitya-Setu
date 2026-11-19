/**
 * Text helpers for mixed Gujarati / English content.
 */

const GUJARATI = /[઀-૿]/g;
const LATIN = /[A-Za-z]/g;
const GUJARATI_DIGITS = "૦૧૨૩૪૫૬૭૮૯";

/**
 * "gu" when the text contains Gujarati script, else "en". For lang attributes.
 * Same rule as the backend's detect_language: Gujarati text routinely mixes in
 * English names, so presence of the script is the test, not a majority.
 */
export function langOf(text: string | null | undefined): "gu" | "en" {
  return text && /[઀-૿]/.test(text) ? "gu" : "en";
}

/** Share of letters that are Gujarati script, 0..1. */
export function gujaratiShare(text: string): number {
  const gu = text.match(GUJARATI)?.length ?? 0;
  const latin = text.match(LATIN)?.length ?? 0;
  return gu + latin === 0 ? 0 : gu / (gu + latin);
}

export function toLatinDigits(text: string): string {
  return text.replace(/[૦-૯]/g, (d) => String(GUJARATI_DIGITS.indexOf(d)));
}

// ------------------------------------------------------------- citations --

/**
 * Inline page citations in an answer, matching the backend's own pattern
 * (backend/qa/grounding.py `_CITATION_RE`): "(પાનું ૪૨)", "(પાનાં 196-197)",
 * "(page 42)", "(pages 12–14, 20)".
 */
const CITATION = /(પાનું|પાનાં|પાના|પૃષ્ઠ|pages?|p\.)\s*([0-9૦-૯](?:[0-9૦-૯\s,\-‐‑–—]*[0-9૦-૯])?)/giu;

export type AnswerPart =
  | { kind: "text"; text: string }
  | { kind: "cite"; text: string; pages: number[] };

/** Pages named by one citation's number list, e.g. "12–14, 20" -> [12, 13, 14, 20]. */
export function parsePages(numbers: string): number[] {
  const pages: number[] = [];
  for (const piece of toLatinDigits(numbers).split(",")) {
    const range = piece.match(/(\d+)\s*[-‐‑–—]\s*(\d+)/);
    if (range) {
      const from = Number(range[1]);
      const to = Number(range[2]);
      if (to >= from && to - from < 50) {
        for (let p = from; p <= to; p++) pages.push(p);
        continue;
      }
    }
    for (const n of piece.match(/\d+/g) ?? []) pages.push(Number(n));
  }
  return [...new Set(pages)];
}

/** Split one line of an answer into plain text and page citations. */
export function splitCitations(line: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of line.matchAll(CITATION)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ kind: "text", text: line.slice(last, start) });
    parts.push({ kind: "cite", text: match[0], pages: parsePages(match[2] ?? "") });
    last = start + match[0].length;
  }
  if (last < line.length) parts.push({ kind: "text", text: line.slice(last) });
  return parts;
}

/**
 * An English answer line backs its point with the book's Gujarati words:
 * "<point> — “<Gujarati from the book>” (page N)" (backend/qa/prompt_builder.py).
 * Returns the three parts, or null when the line has no Gujarati quote.
 */
const SOURCE_QUOTE = /^(.*?)\s*(?:[—–:]|-{1,2})?\s*[“"]([^“”"]*[઀-૿][^“”"]*)[”"](.*)$/su;

export function splitSourceQuote(line: string): { point: string; quote: string; rest: string } | null {
  const m = line.match(SOURCE_QUOTE);
  if (!m) return null;
  return { point: (m[1] ?? "").trim(), quote: (m[2] ?? "").trim(), rest: (m[3] ?? "").trim() };
}

export interface AnswerBlock {
  kind: "paragraph" | "item" | "heading";
  text: string;
}

/** A short line that is all bold ("**પ્રથમ પેરા**") or a markdown heading. */
const HEADING = /^(?:#{1,6}\s+(.+?)|\*\*([^*]{1,80})\*\*|__([^_]{1,80})__)\s*:?$/u;

/**
 * Generated text (answers, summaries) as paragraphs, list items and short
 * headings. Markdown emphasis markers are dropped.
 */
export function answerBlocks(answer: string): AnswerBlock[] {
  return answer
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const heading = line.match(HEADING);
      if (heading) {
        const text = (heading[1] ?? heading[2] ?? heading[3] ?? "").replace(/\*\*|__/g, "").trim();
        return { kind: "heading" as const, text };
      }
      const plain = line.replace(/\*\*|__/g, "");
      const item = plain.match(/^(?:[-*•]|\d+[.)]|[૦-૯]+[.)])\s+(.*)$/u);
      return item ? { kind: "item" as const, text: item[1] ?? "" } : { kind: "paragraph" as const, text: plain };
    })
    .filter((block) => block.text);
}

/** Quoted spans in a piece of answer text: “…”, "…", ‘…’, «…». */
export function quotedSpans(text: string): string[] {
  const spans: string[] = [];
  for (const m of text.matchAll(/[“"«]([^”"»]{4,})[”"»]|‘([^’]{4,})’/gu)) {
    const span = (m[1] ?? m[2] ?? "").trim();
    if (span) spans.push(span);
  }
  return spans;
}

// ------------------------------------------------------------ highlighting --

export interface Span {
  start: number;
  end: number;
}

/**
 * Where each needle occurs in `text`, ignoring differences in whitespace.
 * Returns ranges in the original text, merged and sorted.
 */
export function findSpans(text: string, needles: string[]): Span[] {
  // Collapse whitespace runs to one space, remembering where each kept
  // character came from.
  const map: number[] = [];
  let flat = "";
  let inSpace = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]!;
    if (/\s/.test(ch)) {
      if (!inSpace && flat.length) {
        flat += " ";
        map.push(i);
      }
      inSpace = true;
    } else {
      flat += ch;
      map.push(i);
      inSpace = false;
    }
  }

  const spans: Span[] = [];
  for (const raw of needles) {
    const needle = raw.replace(/\s+/g, " ").trim();
    if (needle.length < 4) continue;
    let from = 0;
    for (;;) {
      const at = flat.indexOf(needle, from);
      if (at < 0) break;
      spans.push({ start: map[at]!, end: map[at + needle.length - 1]! + 1 });
      from = at + needle.length;
    }
  }

  spans.sort((a, b) => a.start - b.start);
  const merged: Span[] = [];
  for (const span of spans) {
    const prev = merged[merged.length - 1];
    if (prev && span.start <= prev.end) prev.end = Math.max(prev.end, span.end);
    else merged.push({ ...span });
  }
  return merged;
}
