import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { answerAsText, copyText } from "../../lib/copy";
import { canRetry, describeError } from "../../lib/errors";
import { Notice } from "../../components/Notice";
import { Elapsed, useElapsed } from "../../components/Progress";
import { formatAskedAt, formatDuration, plural } from "../../lib/format";
import { bookTitle } from "../../api/queries";
import { langOf } from "../../lib/text";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { useBook } from "../../pages/BookPage";
import { AnswerText } from "./AnswerText";
import { QuestionForm } from "./QuestionForm";
import { useQuestionLog } from "./questionLog";
import { SourceList } from "./SourceList";
import { t } from "../../i18n";

/**
 * One question, reopened: the answer with its page citations and, beside it
 * on wide screens (below it on narrow ones), the passages it was written from.
 * Everything shown is what this browser saved when the question was answered.
 */
export function AnswerView() {
  const { entryId = "" } = useParams<{ entryId: string }>();
  const book = useBook();
  const { session } = useAuth();
  const log = useQuestionLog(session?.user.id ?? "anonymous", book.doc_id);
  const navigate = useNavigate();
  const wide = useMediaQuery("(min-width: 1100px)");
  const [selection, setSelection] = useState<{ pages: number[]; token: number }>({ pages: [], token: 0 });
  // The citation under the pointer or keyboard focus, so its passage can be lit.
  const [preview, setPreview] = useState<number[] | null>(null);

  const entry = log.entries.find((e) => e.id === entryId);

  if (!entry) {
    return (
      <div className="answer-view">
        <BackToQuestions />
        <EmptyState title={t("answer.missingTitle")} action={<Link to="../history">{t("answer.backToQuestions")}</Link>}>
          <p>{t("answer.missingBody")}</p>
        </EmptyState>
      </div>
    );
  }

  const result = entry.result;
  const found = Boolean(result?.found);
  const meta = [formatAskedAt(entry.askedAt)];
  if (result) meta.push(t("ask.answeredIn", { time: formatDuration(result.elapsed_seconds) }));

  const sources = result?.found ? (
    <>
      <SourceList
        result={result}
        activePages={selection.pages}
        focusToken={selection.token}
        linkedPages={preview ?? []}
      />
      <p className="sources__limit">{t("sources.limitation")}</p>
    </>
  ) : null;

  return (
    <div className={`answer-view${wide && found ? " answer-view--margin" : ""}`}>
      <article className="answer-view__main" aria-busy={entry.status === "pending"}>
        <BackToQuestions />
        <header className="answer-view__head">
          <h2 className="answer-view__question" lang={langOf(entry.question)}>
            {entry.question}
          </h2>
          <p className="answer-view__meta">{meta.join(", ")}</p>
        </header>

        {entry.status === "pending" && (
          <div className="pending" role="status">
            <span className="reading-lines" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            <p className="pending__line">
              {t("ask.pending")} <Elapsed since={entry.askedAt} />
            </p>
            <PendingHint since={entry.askedAt} />
          </div>
        )}

        {entry.status === "error" && entry.error && (
          <Notice tone="error" title={t("answer.failedTitle")}>
            <p>{describeError(new ApiError(entry.error.status, entry.error.message))}</p>
            {canRetry(new ApiError(entry.error.status, entry.error.message)) && (
              <Button variant="quiet" className="notice__action" onClick={() => log.retry(entry.id)} disabled={log.pending}>
                {t("ask.retryQuestion")}
              </Button>
            )}
          </Notice>
        )}

        {result && !result.found && (
          <div className="refusal">
            <p className="refusal__title">{t("ask.notFoundTitle")}</p>
            <p className="refusal__text" lang={langOf(result.answer)}>
              {result.answer}
            </p>
            <p className="refusal__hint">{t("ask.notFoundHint")}</p>
          </div>
        )}

        {result?.found && (
          <>
            {result.citations.length > 0 && (
              <p className="provenance">
                {/* A small arch: the answer bridged to its passages. */}
                <svg className="provenance__mark" width="22" height="12" viewBox="0 0 22 12" aria-hidden="true">
                  <path d="M2 10.5C4 3 18 3 20 10.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  <circle cx="2" cy="10.5" r="1.6" fill="currentColor" />
                  <circle cx="20" cy="10.5" r="1.6" fill="currentColor" />
                </svg>
                <span>{t("answer.provenance", { passages: plural(result.citations.length, "passage", "passages") })}</span>{" "}
                <cite className="provenance__book" lang={langOf(bookTitle(book))}>
                  {bookTitle(book)}
                </cite>
              </p>
            )}
            <AnswerText
              answer={result.answer}
              language={result.language}
              onCite={(pages) => setSelection((s) => ({ pages, token: s.token + 1 }))}
              activePages={selection.pages}
              onPreview={setPreview}
            />
          </>
        )}

        {entry.status !== "pending" && (
          <div className="answer-view__actions">
            {result?.found && (
              <CopyAnswer text={() => answerAsText(result.answer, result.citations, bookTitle(book))} />
            )}
            <Button
              variant="quiet"
              className="button--small"
              onClick={() => {
                log.remove(entry.id);
                navigate("../history");
              }}
            >
              {t("ask.remove")}
            </Button>
          </div>
        )}

        {!wide && sources && (
          <section className="answer-view__sources" aria-labelledby="sources-title">
            <h3 id="sources-title" className="sources-title">
              {t("sources.title")}
            </h3>
            {sources}
          </section>
        )}

        <section className="follow-up" aria-labelledby="follow-up-title">
          <h3 id="follow-up-title" className="sources-title">
            {t("answer.followUp")}
          </h3>
          <QuestionForm
            disabled={log.pending}
            onAsk={(question) => navigate(`../questions/${log.ask(question)}`)}
          />
        </section>
      </article>

      {wide && sources && (
        <aside className="margin" aria-labelledby="margin-title">
          <div className="margin__inner">
            <h3 id="margin-title" className="sources-title">
              {t("sources.title")}
            </h3>
            <p className="margin__hint">{t("sources.hint")}</p>
            {sources}
          </div>
        </aside>
      )}
    </div>
  );
}

/** After a while, say plainly that waiting longer is normal, and that leaving is safe. */
function PendingHint({ since }: { since: number }) {
  const seconds = useElapsed(since);
  return <p className="pending__hint">{seconds < 40 ? t("ask.pendingHint") : t("ask.pendingLong")}</p>;
}

type CopyState = "idle" | "copied" | "failed";

/** Copy the answer, its page references and its sources; say briefly whether it worked. */
function CopyAnswer({ text }: { text: () => string }) {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copy() {
    const ok = await copyText(text());
    setState(ok ? "copied" : "failed");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), ok ? 2000 : 5000);
  }

  return (
    <>
      <Button variant="quiet" className={`button--small copy${state === "copied" ? " copy--done" : ""}`} onClick={() => void copy()}>
        {state === "copied" ? (
          <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M4.5 10.5l3.5 3.5 7.5-8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <rect x="7" y="7" width="9.5" height="9.5" rx="1.8" stroke="currentColor" strokeWidth="1.5" />
            <path d="M13 7V5.3A1.8 1.8 0 0011.2 3.5H5.3A1.8 1.8 0 003.5 5.3v5.9A1.8 1.8 0 005.3 13H7" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        )}
        {state === "copied" ? t("answer.copied") : t("answer.copy")}
      </Button>
      <span className="copy__status" role="status" aria-live="polite">
        {state === "copied" ? t("answer.copiedStatus") : state === "failed" ? t("answer.copyFailed") : ""}
      </span>
    </>
  );
}

function BackToQuestions() {
  return (
    <Link to="../history" className="crumb">
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M12 4.5L6.5 10l5.5 5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {t("answer.backToQuestions")}
    </Link>
  );
}
