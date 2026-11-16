/**
 * Copying an answer out of the app: the answer as plain text that still reads
 * well (paragraphs, list items, the inline page references), followed by the
 * passages it cites, so it stays checkable wherever it is pasted.
 */
import type { Citation } from "../api/types";
import { formatPages } from "./format";
import { answerBlocks } from "./text";

export function answerAsText(answer: string, citations: Pick<Citation, "page_start" | "page_end" | "chapter_title">[], bookTitle: string): string {
  const lines: string[] = [];
  let previous: string | null = null;
  for (const block of answerBlocks(answer)) {
    // A blank line between paragraphs; list items stay together.
    if (previous && !(previous === "item" && block.kind === "item")) lines.push("");
    lines.push(block.kind === "item" ? `• ${block.text}` : block.text);
    previous = block.kind;
  }

  if (citations.length) {
    lines.push("", `Sources: ${bookTitle}`);
    for (const c of citations) {
      lines.push(c.chapter_title ? `${formatPages(c.page_start, c.page_end)}, ${c.chapter_title}` : formatPages(c.page_start, c.page_end));
    }
  }
  return lines.join("\n");
}

/**
 * Put text on the clipboard. Uses the Clipboard API where the page is allowed
 * to; otherwise (older browsers, or the app served over plain http on a
 * phone) a hidden textarea and the copy command. Resolves false on failure.
 */
export async function copyText(text: string): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* fall through to the older route */
    }
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "0";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    area.setSelectionRange(0, text.length);
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}
