import { Fragment, type ReactNode } from "react";
import { answerBlocks, langOf, splitCitations, type AnswerPart } from "../../lib/text";
import { t } from "../../i18n";

interface AnswerTextProps {
  answer: string;
  /** Called with the pages a citation names. */
  onCite?: (pages: number[]) => void;
  /** Pages currently shown in the sources, to mark their citations. */
  activePages?: number[];
  /** Called while a citation is hovered or focused (null when it is left), to point at its passage. */
  onPreview?: (pages: number[] | null) => void;
}

/** An answer (the app's words, so set in sans), with each "(પાનું ૪૨)" / "(page 42)" turned into a button. */
export function AnswerText({ answer, onCite, activePages = [], onPreview }: AnswerTextProps) {
  const blocks = answerBlocks(answer);

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

  // Consecutive list items render as one list.
  const out: ReactNode[] = [];
  let items: ReactNode[] = [];
  const flush = () => {
    if (items.length) out.push(<ul key={`list-${out.length}`} className="answer__list">{items}</ul>);
    items = [];
  };
  blocks.forEach((block, i) => {
    if (block.kind === "item") {
      items.push(<li key={i}>{render(block.text)}</li>);
    } else {
      flush();
      const className = block.kind === "heading" ? "text-heading" : undefined;
      out.push(<p key={i} className={className}>{render(block.text)}</p>);
    }
  });
  flush();

  return (
    <div className="answer" lang={langOf(answer)}>
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
