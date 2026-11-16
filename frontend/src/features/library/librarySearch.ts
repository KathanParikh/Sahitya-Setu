/** Searching and ordering for the library page. */
import { bookTitle } from "../../api/queries";
import type { BookDocument } from "../../api/types";

/** Lower-case, collapse spaces, and drop Unicode marks that IMEs type inconsistently (ZWJ/ZWNJ). */
function normalise(text: string): string {
  return text.normalize("NFC").replace(/[‌‍]/g, "").replace(/\s+/g, " ").trim().toLowerCase();
}

/** Books whose title, author or file name contains every word of the query. */
export function searchBooks<T extends BookDocument>(books: T[], query: string): T[] {
  const words = normalise(query).split(" ").filter(Boolean);
  if (!words.length) return books;
  return books.filter((book) => {
    const haystack = normalise([bookTitle(book), book.author ?? "", book.filename].join(" "));
    return words.every((word) => haystack.includes(word));
  });
}

/** Newest first, by upload time. */
export function newestFirst<T extends BookDocument>(books: T[]): T[] {
  return [...books].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

/** By title in Gujarati order: Gujarati titles first, then English ones A–Z. */
export function byTitle<T extends BookDocument>(books: T[]): T[] {
  const collator = new Intl.Collator(["gu", "en"], { sensitivity: "base", numeric: true });
  return [...books].sort((a, b) => collator.compare(bookTitle(a), bookTitle(b)));
}
