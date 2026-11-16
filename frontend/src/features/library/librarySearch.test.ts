import { describe, expect, it } from "vitest";
import { bookTitle } from "../../api/queries";
import type { BookDocument } from "../../api/types";
import { byTitle, newestFirst, searchBooks } from "./librarySearch";

function book(doc_id: string, fields: Partial<BookDocument> = {}): BookDocument {
  return {
    doc_id,
    user_id: null,
    filename: `${doc_id}.pdf`,
    title: null,
    author: null,
    page_count: 0,
    chunk_count: 0,
    chapter_count: 0,
    status: "ready",
    progress: null,
    error: null,
    file_path: null,
    extraction_stats: {},
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
    ...fields,
  };
}

const books = [
  book("a", { title: "ગામનું પાદર", author: "Kanaiyalal Munshi", created_at: "2026-11-02T00:00:00Z" }),
  book("b", { title: "Saraswatichandra", author: "ગોવર્ધનરામ ત્રિપાઠી", created_at: "2026-11-03T00:00:00Z" }),
  book("c", { filename: "bhina-pustako.pdf", created_at: "2026-11-01T00:00:00Z" }),
];

describe("searchBooks", () => {
  it("returns everything for an empty query", () => {
    expect(searchBooks(books, "   ")).toHaveLength(3);
  });

  it("matches title, author and file name, ignoring case", () => {
    expect(searchBooks(books, "SARASWATI").map((b) => b.doc_id)).toEqual(["b"]);
    expect(searchBooks(books, "munshi").map((b) => b.doc_id)).toEqual(["a"]);
    expect(searchBooks(books, "pustako").map((b) => b.doc_id)).toEqual(["c"]);
  });

  it("matches Gujarati and needs every word", () => {
    expect(searchBooks(books, "ગામનું").map((b) => b.doc_id)).toEqual(["a"]);
    expect(searchBooks(books, "ગામનું saraswati")).toEqual([]);
  });

  it("ignores zero-width joiners typed by Gujarati keyboards", () => {
    expect(searchBooks(books, "ગામ‍નું").map((b) => b.doc_id)).toEqual(["a"]);
  });
});

describe("ordering", () => {
  it("sorts newest first", () => {
    expect(newestFirst(books).map((b) => b.doc_id)).toEqual(["b", "a", "c"]);
  });

  it("sorts by display title, Gujarati titles before English ones", () => {
    expect(byTitle(books).map((b) => b.doc_id)).toEqual(["a", "c", "b"]);
  });
});

describe("bookTitle", () => {
  it("prefers the PDF title", () => {
    expect(bookTitle({ title: "  ગામનું પાદર ", filename: "x.pdf" })).toBe("ગામનું પાદર");
  });

  it("reads a file name's underscores and hyphens as spaces", () => {
    expect(bookTitle({ title: null, filename: "gujarati_test_book.PDF" })).toBe("gujarati test book");
    expect(bookTitle({ title: "", filename: "bhina-pustako--part_2.pdf" })).toBe("bhina pustako part 2");
  });

  it("treats a title that is just the file name's stem as a file name", () => {
    expect(bookTitle({ title: "gujarati_test_book", filename: "gujarati_test_book.pdf" })).toBe("gujarati test book");
    expect(bookTitle({ title: "Real_Title", filename: "scan.pdf" })).toBe("Real_Title");
  });

  it("falls back to the raw file name when nothing else is left", () => {
    expect(bookTitle({ title: null, filename: "___.pdf" })).toBe("___.pdf");
  });
});
