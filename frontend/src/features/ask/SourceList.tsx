import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Citation } from "../../api/types";
import { formatPages } from "../../lib/format";
import { findSpans, langOf, quotedSpans } from "../../lib/text";
import type { StoredAnswer } from "./questionLog";
import { t } from "../../i18n";

interface SourceListProps {
  result: StoredAnswer;
  /** Pages the reader clicked in the answer; matching passages are marked. */
  activePages: number[];
  /** Changes on every citation click, so the same page can be scrolled to again. */
  focusToken: number;
  /** Pages of the citation being hovered or focused in the answer; matching passages are lit. */
  linkedPages?: number[];
}

function covers(citation: Citation, pages: number[]): boolean {
  return pages.some((p) => p >= citation.page_start && p <= citation.page_end);
}

/** Text with the given spans wrapped in <mark>. */
function highlighted(text: string, needles: string[]): ReactNode {
  const spans = findSpans(text, needles);
  if (!spans.length) return text;
  const out: ReactNode[] = [];
  let last = 0;
  spans.forEach((span, i) => {
    if (span.start > last) out.push(text.slice(last, span.start));
    out.push(<mark key={i}>{text.slice(span.start, span.end)}</mark>);
    last = span.end;
  });
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** The passages an answer was written from, with quoted words highlighted. */
export function SourceList({ result, activePages, focusToken, linkedPages = [] }: SourceListProps) {
  const quotes = useMemo(() => quotedSpans(result.answer), [result.answer]);
  const listRef = useRef<HTMLOListElement>(null);

  // Bring the first matching passage into view after a citation click. Only
  // when this copy of the list is on screen (desktop panel or mobile inline).
  useEffect(() => {
    const list = listRef.current;
    if (!list || !activePages.length || list.offsetParent === null) return;
    const target = list.querySelector<HTMLElement>(".source--active");
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target?.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "nearest" });
    target?.focus({ preventScroll: true });
  }, [focusToken, activePages]);

  if (!result.citations.length) return <p className="muted sources__empty">{t("sources.none")}</p>;

  return (
    <ol ref={listRef} className="sources">
      {result.citations.map((citation, i) => {
        const active = covers(citation, activePages);
        return (
          <SourceItem
            // A new key on each citation click replays the highlight, even for the same page.
            key={active ? `${citation.chunk_id}:${focusToken}` : citation.chunk_id}
            citation={citation}
            text={result.contexts[i] ?? citation.snippet}
            quotes={quotes}
            active={active}
            linked={!active && covers(citation, linkedPages)}
          />
        );
      })}
    </ol>
  );
}

function SourceItem({
  citation,
  text,
  quotes,
  active,
  linked,
}: {
  citation: Citation;
  text: string;
  quotes: string[];
  active: boolean;
  linked: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const open = expanded || active;
  const body = useMemo(() => highlighted(text, quotes), [text, quotes]);

  return (
    <li className={`source${active ? " source--active" : ""}${linked ? " source--linked" : ""}`} tabIndex={-1}>
      <p className="source__meta">
        <span className="source__pages">{formatPages(citation.page_start, citation.page_end)}</span>
        {citation.chapter_title && (
          <span className="source__chapter" lang={langOf(citation.chapter_title)}>
            {citation.chapter_title}
          </span>
        )}
      </p>
      <blockquote className={`source__text book-text${open ? "" : " source__text--clamped"}`} lang={langOf(text)}>
        {body}
      </blockquote>
      {!active && (
        <p className="source__foot">
          <button type="button" className="text-button" onClick={() => setExpanded((v) => !v)} aria-expanded={open}>
            {open ? t("sources.showLess") : t("sources.showMore")}
          </button>
        </p>
      )}
    </li>
  );
}
