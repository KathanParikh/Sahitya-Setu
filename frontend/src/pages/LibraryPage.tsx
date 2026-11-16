import { useMemo, useState, type DragEvent } from "react";
import { bookTitle, isBusy, useDeleteDocument, useDocuments } from "../api/queries";
import type { BookDocument } from "../api/types";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ErrorMessage, describeError } from "../components/ErrorMessage";
import { Notice } from "../components/Notice";
import { ReadingJourney, WordsToMeaning } from "../components/Visuals";
import { BookList, BookListPlaceholder } from "../features/library/BookList";
import { byTitle, newestFirst, searchBooks } from "../features/library/librarySearch";
import { UploadButton, UploadPanel, useSharedUploader } from "../features/library/UploadControl";
import { plural } from "../lib/format";
import { langOf } from "../lib/text";
import { t } from "../i18n";

type Order = "newest" | "title";

/**
 * The library: what this workspace is, where a new book goes in, and the
 * books already here, in one centred column.
 */
export function LibraryPage() {
  const documents = useDocuments();
  const uploader = useSharedUploader();
  const remove = useDeleteDocument();
  const [toDelete, setToDelete] = useState<BookDocument | null>(null);
  const [dragging, setDragging] = useState(false);
  const [query, setQuery] = useState("");
  const [order, setOrder] = useState<Order>("newest");

  const books = useMemo(() => newestFirst(documents.data ?? []), [documents.data]);
  const searching = query.trim().length > 0;
  const shown = useMemo(() => {
    const found = searchBooks(books, query);
    return order === "title" ? byTitle(found) : found;
  }, [books, query, order]);
  const processing = books.filter((b) => isBusy(b.status)).length;

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file && !uploader.busy) uploader.choose(file);
  }

  return (
    <div
      className="container library view"
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={onDrop}
    >
      {/* The intro, with the words-to-meaning composition as its second column on wide screens. */}
      <div className="library__head">
        <header className="library__intro">
          <h1 className="page-title">{t("library.title")}</h1>
          <p className="library__lead">{t("library.subtitle")}</p>
        </header>
        <WordsToMeaning className="library__words" />
      </div>

      <div className="library__main">
        <section
          className={`upload${dragging ? " upload--over" : ""}${uploader.state.phase !== "idle" ? " upload--active" : ""}`}
          aria-labelledby={uploader.state.phase === "idle" ? "upload-title" : undefined}
        >
          {uploader.state.phase === "idle" ? (
            <div className="upload__idle">
              <div className="upload__text">
                <h2 id="upload-title" className="upload__title">
                  {dragging ? t("upload.dropHere") : t("upload.title")}
                </h2>
                <p className="upload__hint">{t("upload.hint")}</p>
              </div>
              <UploadButton uploader={uploader} />
            </div>
          ) : (
            <UploadPanel uploader={uploader} />
          )}
        </section>

        <section className="books" aria-labelledby="books-heading">
          <div className="books__head">
            <div className="books__heading">
              <h2 id="books-heading" className="books__title" aria-live={searching ? "polite" : undefined}>
                {searching
                  ? shown.length
                    ? t("library.results", { count: plural(shown.length, "book", "books"), query: query.trim() })
                    : t("library.noResults", { query: query.trim() })
                  : t("library.shelf")}
              </h2>
              {!searching && documents.isSuccess && books.length > 0 && (
                <p className="books__count">{libraryCount(books.length, processing)}</p>
              )}
            </div>
            {books.length > 0 && (
              <div className="books__tools">
                <div className="search" role="search">
                  <label htmlFor="library-search" className="visually-hidden">
                    {t("library.searchLabel")}
                  </label>
                  <svg className="search__icon" width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                    <circle cx="8.75" cy="8.75" r="5.25" stroke="currentColor" strokeWidth="1.6" />
                    <path d="M12.75 12.75l3.75 3.75" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                  </svg>
                  <input
                    id="library-search"
                    type="search"
                    className="search__input"
                    placeholder={t("library.searchPlaceholder")}
                    value={query}
                    lang={langOf(query)}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && setQuery("")}
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
                {books.length > 1 && (
                  <div className="segmented" role="radiogroup" aria-label={t("library.sortLabel")}>
                    {(["newest", "title"] as const).map((value) => (
                      <button
                        key={value}
                        type="button"
                        role="radio"
                        aria-checked={order === value}
                        className="segmented__option"
                        onClick={() => setOrder(value)}
                      >
                        {value === "newest" ? t("library.sortNewest") : t("library.sortTitle")}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {documents.isPending && <BookListPlaceholder />}

          {documents.isError && (
            <ErrorMessage error={documents.error} title={t("library.loadFailed")} onRetry={() => void documents.refetch()} />
          )}

          {documents.isSuccess && books.length === 0 && (
            <div className="state state--inline empty-library">
              <ReadingJourney still className="empty-library__picture" />
              <div className="empty-library__text">
                <p className="state__title">{t("library.emptyTitle")}</p>
                <p className="state__body">{t("library.emptyBody")}</p>
              </div>
            </div>
          )}

          {shown.length > 0 && <BookList books={shown} onDelete={setToDelete} />}

          {searching && shown.length === 0 && (
            <div className="state state--inline" aria-live="polite">
              <p className="state__body">{t("library.noResultsHint")}</p>
              <Button className="button--small state__action" onClick={() => setQuery("")}>
                {t("library.clearSearch")}
              </Button>
            </div>
          )}
        </section>
      </div>

      <ConfirmDialog
        open={toDelete !== null}
        title={t("library.deleteTitle")}
        confirmLabel={t("library.deleteConfirm")}
        cancelLabel={t("common.cancel")}
        danger
        busy={remove.isPending}
        onCancel={() => {
          setToDelete(null);
          remove.reset();
        }}
        onConfirm={() => {
          if (!toDelete) return;
          remove.mutate(toDelete.doc_id, { onSuccess: () => setToDelete(null) });
        }}
      >
        {toDelete && (
          <>
            <p>
              <span lang={langOf(bookTitle(toDelete))} className="dialog__strong">
                {bookTitle(toDelete)}
              </span>
            </p>
            <p className="muted">{t("library.deleteBody")}</p>
            {remove.isError && <Notice tone="error" title={describeError(remove.error)} />}
          </>
        )}
      </ConfirmDialog>
    </div>
  );
}

function libraryCount(count: number, processing: number): string {
  const books = plural(count, "book", "books");
  return processing ? t("library.leadProcessing", { books, count: processing }) : books;
}
