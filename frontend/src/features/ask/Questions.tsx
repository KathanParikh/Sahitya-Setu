import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import type { BookDetail } from "../../api/types";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { formatAskedAt, plural } from "../../lib/format";
import { langOf } from "../../lib/text";
import { useBook } from "../../pages/BookPage";
import { Chevron } from "../library/BookList";
import { QuestionForm } from "./QuestionForm";
import { useQuestionLog, type LogEntry } from "./questionLog";
import { t } from "../../i18n";

/** The signed-in reader's saved questions for the open book. */
export function useBookQuestions() {
  const book = useBook();
  const { session } = useAuth();
  return { book, log: useQuestionLog(session?.user.id ?? "anonymous", book.doc_id) };
}

const RECENT = 3;

/**
 * Ask: the question box first. Below it, a few questions to start with, or
 * the latest questions asked, with the way to the full history.
 */
export function AskTab() {
  const { book, log } = useBookQuestions();
  const navigate = useNavigate();
  const newestFirst = [...log.entries].reverse();

  function ask(question: string) {
    navigate(`questions/${log.ask(question)}`);
  }

  return (
    <div className="questions">
      <section className="ask-new" aria-labelledby="ask-new-title">
        <h2 id="ask-new-title" className="section-title">
          {t("ask.newTitle")}
        </h2>
        <p className="section-lead">{t("ask.newBody")}</p>
        <QuestionForm disabled={log.pending} onAsk={ask} />
      </section>

      {newestFirst.length > 0 ? (
        <section className="history" aria-labelledby="recent-title">
          <div className="history__head">
            <h2 id="recent-title" className="section-title">
              {t("ask.recentTitle")}
            </h2>
            <Link to="history" className="history__all">
              {t("ask.viewAll", { count: newestFirst.length })}
            </Link>
          </div>
          <QuestionTable entries={newestFirst.slice(0, RECENT)} />
        </section>
      ) : (
        <Starters book={book} disabled={log.pending} onAsk={ask} />
      )}
    </div>
  );
}

/** History: every saved question for this book, newest first, with a filter. */
export function HistoryTab() {
  const { log } = useBookQuestions();
  const [filter, setFilter] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const newestFirst = useMemo(() => [...log.entries].reverse(), [log.entries]);
  const shown = useMemo(() => {
    const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return newestFirst;
    return newestFirst.filter((e) => {
      const text = `${e.question} ${e.result?.answer ?? ""}`.toLowerCase();
      return words.every((w) => text.includes(w));
    });
  }, [newestFirst, filter]);

  if (!newestFirst.length) {
    return (
      <div className="questions">
        <div className="state">
          <h2 className="state__title">{t("history.emptyTitle")}</h2>
          <p className="state__body">{t("history.emptyBody")}</p>
          <Link to=".." className="button button--primary state__action">
            {t("history.emptyAction")}
          </Link>
          <p className="state__note">{t("ask.storedLocally")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="questions">
      <section className="history" aria-labelledby="history-title">
        <div className="history__head">
          <h2 id="history-title" className="section-title">
            {t("ask.logTitle")} <span className="history__count">{newestFirst.length}</span>
          </h2>
          <div className="history__tools">
            {newestFirst.length > 3 && (
              <div className="search" role="search">
                <label htmlFor="history-filter" className="visually-hidden">
                  {t("history.filterLabel")}
                </label>
                <svg className="search__icon" width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <circle cx="8.75" cy="8.75" r="5.25" stroke="currentColor" strokeWidth="1.6" />
                  <path d="M12.75 12.75l3.75 3.75" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
                <input
                  id="history-filter"
                  type="search"
                  className="search__input"
                  placeholder={t("history.filterPlaceholder")}
                  value={filter}
                  lang={langOf(filter)}
                  onChange={(e) => setFilter(e.target.value)}
                  onKeyDown={(e) => e.key === "Escape" && setFilter("")}
                  autoComplete="off"
                />
              </div>
            )}
            <Button
              variant="quiet"
              className="button--small"
              onClick={() => setConfirmClear(true)}
              disabled={log.entries.every((e) => e.status === "pending")}
            >
              {t("ask.clear")}
            </Button>
          </div>
        </div>

        {shown.length ? (
          <QuestionTable entries={shown} withHead />
        ) : (
          <div className="state state--inline" aria-live="polite">
            <p className="state__title">{t("history.noMatchTitle", { query: filter.trim() })}</p>
            <p className="state__body">{t("history.noMatchBody")}</p>
            <Button className="button--small state__action" onClick={() => setFilter("")}>
              {t("library.clearSearch")}
            </Button>
          </div>
        )}
        <p className="history__note">{t("ask.storedLocally")}</p>
      </section>

      <ConfirmDialog
        open={confirmClear}
        title={t("ask.clearTitle")}
        confirmLabel={t("ask.clearConfirm")}
        cancelLabel={t("common.cancel")}
        danger
        onCancel={() => setConfirmClear(false)}
        onConfirm={() => {
          log.clear();
          setConfirmClear(false);
        }}
      >
        <p className="muted">{t("ask.clearBody")}</p>
      </ConfirmDialog>
    </div>
  );
}

/** Questions as rows: the question and a line of its answer, when, and the outcome. */
function QuestionTable({ entries, withHead }: { entries: LogEntry[]; withHead?: boolean }) {
  return (
    <div className="q-table">
      {withHead && (
        <div className="q-table__head" aria-hidden="true">
          <span>{t("ask.colQuestion")}</span>
          <span>{t("ask.colAsked")}</span>
          <span>{t("ask.colAnswer")}</span>
          <span />
        </div>
      )}
      <ul>
        {entries.map((entry) => (
          <QuestionRow key={entry.id} entry={entry} />
        ))}
      </ul>
    </div>
  );
}

/** The answer as one plain line: page citations dropped, spaces collapsed. */
function excerpt(answer: string): string {
  return answer
    .replace(/\s*\((?:પાનું|પાનાં|પાના|પૃષ્ઠ|pages?|p\.)[^)]*\)/giu, "")
    .replace(/[#*_>`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function QuestionRow({ entry }: { entry: LogEntry }) {
  const book = useBook();
  const result = entry.result;
  let status: string;
  let tone = "";
  if (entry.status === "pending") {
    status = t("ask.statusPending");
    tone = "pending";
  } else if (entry.status === "error") {
    status = t("ask.statusError");
    tone = "error";
  } else if (result && !result.found) {
    status = t("ask.statusNotFound");
    tone = "not-found";
  } else {
    status = plural(result?.citations.length ?? 0, "source", "sources");
  }
  const preview = result?.found ? excerpt(result.answer) : "";

  return (
    <li className={`q-row${tone ? ` q-row--${tone}` : ""}`}>
      {/* An absolute path, so the row works from whichever tab lists it. */}
      <Link to={`/books/${encodeURIComponent(book.doc_id)}/questions/${entry.id}`} className="q-row__link">
        <span className="q-row__main">
          <span className="q-row__question" lang={langOf(entry.question)}>
            {entry.question}
          </span>
          {preview && (
            <span className="q-row__preview" lang={langOf(preview)}>
              {preview}
            </span>
          )}
        </span>
        <span className="q-row__date">{formatAskedAt(entry.askedAt)}</span>
        <span className="q-row__status">
          {entry.status === "pending" && <span className="spinner" aria-hidden="true" />}
          {status}
        </span>
        <Chevron />
      </Link>
    </li>
  );
}

/** Questions most works of Gujarati literature can answer, and one about the first chapter. */
function starterQuestions(book: BookDetail): string[] {
  const list: string[] = [];
  const first = book.chapters[0]?.title?.trim();
  if (first && first.length <= 60) {
    list.push(langOf(first) === "gu" ? `“${first}” પ્રકરણમાં શું બને છે?` : `What happens in “${first}”?`);
  }
  list.push("આ પુસ્તકનાં મુખ્ય પાત્રો કોણ છે?");
  list.push("આ પુસ્તકનો મુખ્ય વિચાર શો છે?");
  list.push("What is this book about, in brief?");
  return list.slice(0, 4);
}

/** Before the first question: a few questions to begin with. */
function Starters({ book, disabled, onAsk }: { book: BookDetail; disabled: boolean; onAsk: (q: string) => void }) {
  return (
    <section className="history" aria-labelledby="starters-title">
      <h2 id="starters-title" className="section-title">
        {t("ask.startersTitle")}
      </h2>
      <p className="section-lead">{t("ask.emptyBody")}</p>
      <div className="q-table">
        <ul>
          {starterQuestions(book).map((question) => (
            <li key={question} className="q-row q-row--starter">
              <button
                type="button"
                className="q-row__link"
                lang={langOf(question)}
                disabled={disabled}
                onClick={() => onAsk(question)}
              >
                <span className="q-row__main">
                  <span className="q-row__question">{question}</span>
                </span>
                <span className="q-row__status">{t("ask.askThis")}</span>
                <Chevron />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
