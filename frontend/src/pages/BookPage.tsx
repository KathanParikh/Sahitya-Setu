import { Link, NavLink, Outlet, useLocation, useOutletContext, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { bookTitle, isBusy, useDocument } from "../api/queries";
import type { BookDetail } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorMessage } from "../components/ErrorMessage";
import { Notice } from "../components/Notice";
import { ProgressBar } from "../components/Progress";
import { Spinner } from "../components/Spinner";
import { formatDate, plural } from "../lib/format";
import { langOf } from "../lib/text";
import { t } from "../i18n";

export interface BookContext {
  book: BookDetail;
}

/** The book whose page is open; for the views under /books/:docId. */
export function useBook(): BookDetail {
  return useOutletContext<BookContext>().book;
}

/**
 * /books/:docId — one book: its name and particulars, then its tabs: Ask,
 * History (the questions asked of it, each opening its answer), Summaries
 * and Contents.
 */
export function BookPage() {
  const { docId = "" } = useParams<{ docId: string }>();
  const query = useDocument(docId);
  const { pathname } = useLocation();

  if (query.isPending) {
    return (
      <div className="container book-state">
        <BackLink />
        <div className="book-head__placeholder" aria-hidden="true">
          <span className="placeholder-line" style={{ width: "40%", height: "1.6rem" }} />
          <span className="placeholder-line placeholder-line--short" style={{ width: "25%" }} />
        </div>
        <Spinner label={t("book.loading")} />
      </div>
    );
  }

  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="container book-state view">
        <BackLink />
        {missing ? (
          <EmptyState level={1} title={t("book.notFoundTitle")} action={<Link to="/">{t("notFound.action")}</Link>}>
            <p>{t("book.notFoundBody")}</p>
          </EmptyState>
        ) : (
          <div className="page-loading">
            <ErrorMessage error={query.error} title={t("book.loadFailed")} onRetry={() => void query.refetch()} />
          </div>
        )}
      </div>
    );
  }

  const book = query.data;
  const title = bookTitle(book);
  const ready = book.status === "ready";
  // An open answer belongs to the history.
  const inHistory = /\/(history|questions\/[^/]+)$/.test(pathname);

  return (
    <div className="book">
      <header className="container book-head view">
        <BackLink />
        <h1 className="page-title book-head__title" lang={langOf(title)}>
          {title}
        </h1>
        <BookFacts book={book} />
      </header>

      {ready ? (
        <>
          <div className="tabs">
            <nav className="container tabs__inner" aria-label={t("book.sections")}>
              <NavLink to="" end className="tabs__link">
                {t("book.tabAsk")}
              </NavLink>
              <NavLink to="history" className={`tabs__link${inHistory ? " active" : ""}`} aria-current={inHistory ? "page" : undefined}>
                {t("book.tabHistory")}
              </NavLink>
              <NavLink to="summaries" className="tabs__link">
                {t("book.tabSummaries")}
              </NavLink>
              <NavLink to="contents" className="tabs__link">
                {t("book.tabContents")}
              </NavLink>
            </nav>
          </div>
          {/* A new key per view replays the arrival fade between tabs and answers. */}
          <div key={pathname} className="container book__body view">
            <Outlet context={{ book } satisfies BookContext} />
          </div>
        </>
      ) : (
        <div className="container book__body">
          <NotReady book={book} />
        </div>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/" className="crumb">
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M12 4.5L6.5 10l5.5 5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {t("nav.library")}
    </Link>
  );
}

function BookFacts({ book }: { book: BookDetail }) {
  const facts: string[] = [];
  if (book.author) facts.push(book.author);
  if (book.status === "ready") {
    facts.push(plural(book.page_count, "page", "pages"));
    facts.push(book.chapter_count ? plural(book.chapter_count, "chapter", "chapters") : t("book.noChapters"));
  }
  facts.push(t("library.uploaded", { date: formatDate(book.created_at) }));
  return (
    <p className="book-head__facts">
      {facts.map((fact, i) => (
        <span key={i} lang={langOf(fact)} className={i === 0 && book.author ? "book-head__author" : undefined}>
          {fact}
        </span>
      ))}
    </p>
  );
}

function NotReady({ book }: { book: BookDetail }) {
  if (isBusy(book.status)) {
    return (
      <div className="processing" aria-live="polite">
        <h2 className="section-title">{t("book.processingTitle")}</h2>
        <p className="processing__step">{book.progress || t("book.processingQueued")}</p>
        <ProgressBar value={null} label={t("book.processingTitle")} />
        <p className="processing__hint">{t("book.processingHint")}</p>
      </div>
    );
  }
  return (
    <Notice tone="error" title={t("book.failedTitle")}>
      <p>{book.error || t("library.failedGeneric")}</p>
      <p className="notice__action">
        <Link to="/">{t("book.failedAction")}</Link>
      </p>
    </Notice>
  );
}
