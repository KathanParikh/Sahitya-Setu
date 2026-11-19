import { Fragment, type ReactNode } from "react";
import type { ContentLanguage } from "../../api/types";
import { answerBlocks, langOf, splitCitations, splitSourceQuote, type AnswerPart } from "../../lib/text";
import { t } from "../../i18n";

interface AnswerTextProps {
  answer: string;
  /**
   * The language the backend answered in. An English answer quotes the book's
   * Gujarati for every point, so guessing from the text would call it Gujarati.
   */
  language?: ContentLanguage;
  /** Called with the pages a citation names. */
  onCite?: (pages: number[]) => void;
  /** Pages currently shown in the sources, to mark their citations. */
  activePages?: number[];
  /** Called while a citation is hovered or focused (null when it is left), to point at its passage. */
  onPreview?: (pages: number[] | null) => void;
}

/** An answer (the app's words, so set in sans), with each "(પાનું ૪૨)" / "(page 42)" turned into a button. */
export function AnswerText({ answer, language, onCite, activePages = [], onPreview }: AnswerTextProps) {
  const blocks = answerBlocks(answer);
  const english = language === "english";
  const lang = english ? "en" : language === "gujarati" ? "gu" : langOf(answer);

  const render = (text: string): ReactNode =>
    unwrapCited(splitCitations(text), Boolean(onCite)).map((part, i) => {
      if (part.kind === "text") return <Fragment key={i}>{part.text}</Fragment>;
      if (!onCite || part.pages.length === 0) return <Fragment key={i}>{part.text}</Fragment>;
      const active = part.pages.some((p) => activePages.includes(p));
      return (
        <button
          key={i}
          type="button"
          className={`cite${active ? " cite--active" : ""}`}
          onClick={() => onCite(part.pages)}
          onMouseEnter={() => onPreview?.(part.pages)}
          onMouseLeave={() => onPreview?.(null)}
          onFocus={() => onPreview?.(part.pages)}
          onBlur={() => onPreview?.(null)}
          aria-pressed={active}
          title={t("ask.showSource")}
        >
          {part.text}
        </button>
      );
    });

  // An English line: the point in English, then the book's own Gujarati
  // words under it, set as book text, with the page citation.
  const renderLine = (text: string): ReactNode => {
    const source = english ? splitSourceQuote(text) : null;
    if (!source) return render(text);
    return (
      <>
        {source.point && render(source.point)}
        <span className="answer__source" lang="gu">
          <span className="answer__source-label" lang="en">{t("answer.fromBook")}</span>
          <q className="answer__quote">{source.quote}</q>
          {source.rest && <> {render(source.rest)}</>}
        </span>
      </>
    );
  };

  // Consecutive list items render as one list.
  const out: ReactNode[] = [];
  let items: ReactNode[] = [];
  const flush = () => {
    if (items.length) out.push(<ul key={`list-${out.length}`} className="answer__list">{items}</ul>);
    items = [];
  };
  blocks.forEach((block, i) => {
    if (block.kind === "item") {
      items.push(<li key={i}>{renderLine(block.text)}</li>);
    } else {
      flush();
      const className = block.kind === "heading" ? "text-heading" : undefined;
      out.push(<p key={i} className={className}>{renderLine(block.text)}</p>);
    }
  });
  flush();

  return (
    <div className="answer" lang={lang}>
      {out}
    </div>
  );
}

/**
 * A citation shown as a chip carries its own edges, so drop the brackets
 * around it: "… મૂક્યાં (પાનું ૧૩૨)." reads "… મૂક્યાં [પાનું ૧૩૨]."
 */
function unwrapCited(parts: AnswerPart[], chips: boolean): AnswerPart[] {
  if (!chips) return parts;
  const out = parts.map((part) => ({ ...part }));
  out.forEach((part, i) => {
    if (part.kind !== "cite" || part.pages.length === 0) return;
    const before = out[i - 1];
    const after = out[i + 1];
    if (before?.kind === "text" && after?.kind === "text" && /\(\s*$/.test(before.text) && /^\s*\)/.test(after.text)) {
      before.text = before.text.replace(/\(\s*$/, "");
      after.text = after.text.replace(/^\s*\)/, "");
    }
  });
  return out;
}
