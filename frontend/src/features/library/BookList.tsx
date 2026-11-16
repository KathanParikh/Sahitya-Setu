import { Link } from "react-router-dom";
import { bookTitle, isBusy } from "../../api/queries";
import type { BookDocument } from "../../api/types";
import { formatDate } from "../../lib/format";
import { langOf } from "../../lib/text";
import { t } from "../../i18n";
import { BookStatus } from "./BookStatus";

type OnDelete = (book: BookDocument) => void;

export const bookPath = (book: BookDocument, tab = "") =>
  `/books/${encodeURIComponent(book.doc_id)}${tab ? `/${tab}` : ""}`;

export function Chevron() {
  return (
    <svg className="chevron" width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M8 4.5l5.5 5.5L8 15.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The books as rows: name and author, date uploaded, status when it matters. */
export function BookList({ books, onDelete }: { books: BookDocument[]; onDelete: OnDelete }) {
  return (
    <div className="book-table">
      <div className="book-table__head" aria-hidden="true">
        <span>{t("library.colName")}</span>
        <span>{t("library.colUploaded")}</span>
        <span />
      </div>
      <ul className="book-table__rows">
        {books.map((book) => (
          <BookRow key={book.doc_id} book={book} onDelete={onDelete} />
        ))}
      </ul>
    </div>
  );
}

function BookRow({ book, onDelete }: { book: BookDocument; onDelete: OnDelete }) {
  const title = bookTitle(book);
  const ready = book.status === "ready";
  const busy = isBusy(book.status);

  return (
    <li className={`book-row book-row--${book.status}`}>
      <div className="book-row__main">
        <h3 className="book-row__title" lang={langOf(title)}>
          {/* The title link stretches over the whole row (see library.css). */}
          {ready ? <Link to={bookPath(book)}>{title}</Link> : title}
        </h3>
        {book.author && (
          <p className="book-row__author" lang={langOf(book.author)}>
            {book.author}
          </p>
        )}
        <BookStatus book={book} />
      </div>
      <p className="book-row__date">
        <time dateTime={book.created_at}>{formatDate(book.created_at)}</time>
      </p>
      <div className="book-row__end">
        <button
          type="button"
          className="book-row__delete"
          onClick={() => onDelete(book)}
          aria-label={t("library.deleteNamed", { title })}
          // Deleting mid-ingestion would race the background job on the server.
          disabled={busy}
          title={busy ? t("library.deleteWhileBusy") : t("library.delete")}
        >
          <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M4 6h12M8 6V4.5h4V6M6 6l.7 10h6.6L14 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {ready ? <Chevron /> : <span className="chevron-space" aria-hidden="true" />}
      </div>
    </li>
  );
}

/** Row-shaped placeholders while the list loads, so the page does not jump. */
export function BookListPlaceholder() {
  return (
    <div className="book-table" aria-hidden="true">
      <ul className="book-table__rows">
        {[62, 48, 70].map((width, i) => (
          <li key={i} className="book-row book-row--placeholder">
            <div className="book-row__main">
              <span className="placeholder-line" style={{ width: `${width}%` }} />
              <span className="placeholder-line placeholder-line--short" style={{ width: `${width / 2}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
