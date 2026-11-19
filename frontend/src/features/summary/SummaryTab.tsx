import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/endpoints";
import { keys } from "../../api/queries";
import type { BookSummary, ChapterSummary, ContentLanguage } from "../../api/types";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";
import { Notice } from "../../components/Notice";
import { Elapsed } from "../../components/Progress";
import { formatPages } from "../../lib/format";
import { answerBlocks, gujaratiShare, langOf } from "../../lib/text";
import { useBook } from "../../pages/BookPage";
import { t } from "../../i18n";

interface Summaries {
  book: BookSummary;
  chapters: ChapterSummary[];
}

/**
 * Whether this browser has loaded this book's summary before, so it is saved
 * on the server and can be shown without spending the summary quota.
 * (The API has no way to ask "is one saved?" without building it.)
 */
const seenKey = (docId: string, language: ContentLanguage) => `ss:summary-seen:${docId}:${language}`;

function seen(docId: string, language: ContentLanguage): boolean {
  try {
    return window.localStorage.getItem(seenKey(docId, language)) === "1";
  } catch {
    return false;
  }
}

function markSeen(docId: string, language: ContentLanguage): void {
  try {
    window.localStorage.setItem(seenKey(docId, language), "1");
  } catch {
    /* fine: the reader will press the button next time */
  }
}

/**
 * The whole-book summary is built from the chapter summaries, so building it
 * also saves every chapter summary; the chapters request after it is then a
 * free read.
 */
async function fetchSummaries(docId: string, language: ContentLanguage, force: boolean): Promise<Summaries> {
  const book = await api.bookSummary(docId, { language, force });
  const chapters = await api.chapterSummaries(docId, { language });
  markSeen(docId, language);
  return { book, chapters: chapters.chapters };
}

/** The language the summary text is actually in. */
function writtenIn(text: string): ContentLanguage {
  return gujaratiShare(text) >= 0.5 ? "gujarati" : "english";
}

const LANGUAGES: { value: ContentLanguage; label: string }[] = [
  { value: "gujarati", label: "ગુજરાતી" },
  { value: "english", label: "English" },
];

export function SummaryTab() {
  const book = useBook();
  const queryClient = useQueryClient();
  const [language, setLanguage] = useState<ContentLanguage>("gujarati");
  const [requested, setRequested] = useState<Record<string, boolean>>({});
  const [confirmRebuild, setConfirmRebuild] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);

  const enabled = requested[language] || seen(book.doc_id, language);

  const query = useQuery({
    queryKey: keys.summary(book.doc_id, language),
    queryFn: () => {
      setStartedAt(Date.now());
      return fetchSummaries(book.doc_id, language, false);
    },
    enabled,
    staleTime: Infinity,
    gcTime: Infinity,
    // Never repeat a build automatically: each one costs quota and minutes.
    retry: false,
  });

  const rebuild = useMutation({
    mutationFn: () => {
      setStartedAt(Date.now());
      return fetchSummaries(book.doc_id, language, true);
    },
    onSuccess: (data) => {
      // Each language is saved separately, so the other language is untouched.
      queryClient.setQueryData(keys.summary(book.doc_id, language), data);
    },
  });

  const working = query.isFetching || rebuild.isPending;
  const data = query.data;
  const actual = data ? writtenIn(data.book.summary) : null;
  const mismatch = data && actual !== language;
  const shown = Boolean(data && !working);
  const current = useCurrentSection(shown, data?.chapters.length ?? 0);
  useScrollToHash(shown);

  return (
    <div className="summaries">
      <div className="summaries__bar">
        <div className="summaries__language">
          <span id="summary-language-label" className="summaries__label">
            {t("summary.language")}
          </span>
          <div className="segmented" role="radiogroup" aria-labelledby="summary-language-label">
            {LANGUAGES.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={language === option.value}
                className="segmented__option"
                lang={option.value === "gujarati" ? "gu" : "en"}
                onClick={() => setLanguage(option.value)}
                disabled={working}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {data && !working && (
          <Button variant="quiet" onClick={() => setConfirmRebuild(true)}>
            {t("summary.rebuild")}
          </Button>
        )}
      </div>

      {working && (
        <div className="summaries__working" role="status">
          <span className="spinner" aria-hidden="true" />
          <span className="summaries__working-title">
            {t("summary.working")} {startedAt && <Elapsed since={startedAt} />}
          </span>
          <p className="muted summaries__working-hint">{t("summary.workingHint")}</p>
        </div>
      )}

      {!enabled && !working && (
        <EmptyState
          title={t("summary.introTitle")}
          action={
            <Button variant="primary" onClick={() => setRequested((r) => ({ ...r, [language]: true }))}>
              {t("summary.show")}
            </Button>
          }
        >
          <p>{t("summary.introBody")}</p>
          <p className="summaries__cost">{t("summary.introCost")}</p>
        </EmptyState>
      )}

      {query.isError && !working && (
        <ErrorMessage error={query.error} title={t("summary.failedTitle")} onRetry={() => void query.refetch()} />
      )}
      {rebuild.isError && !working && (
        <ErrorMessage error={rebuild.error} title={t("summary.rebuildFailedTitle")} onRetry={() => rebuild.mutate()} />
      )}

      {data && !working && (
        <>
          {mismatch && (
            <Notice
              title={
                language === "english" ? t("summary.mismatchEnglishTitle") : t("summary.mismatchGujaratiTitle")
              }
            >
              <p>{t("summary.mismatchBody")}</p>
            </Notice>
          )}

          <div className="summaries__layout">
            {data.chapters.length > 0 && (
              <nav className="summary-rail" aria-label={t("summary.railLabel")}>
                <ol>
                  <li>
                    <a href="#summary-book" className={current === "summary-book" ? "is-current" : undefined}>
                      {t("summary.wholeBook")}
                    </a>
                  </li>
                  {data.chapters.map((chapter) => {
                    const id = `chapter-${chapter.chapter_index}`;
                    return (
                      <li key={id}>
                        <a href={`#${id}`} className={current === id ? "is-current" : undefined}>
                          <span className="summary-rail__number">{chapter.chapter_index + 1}</span>
                          <span lang={langOf(chapter.title)}>{chapter.title}</span>
                        </a>
                      </li>
                    );
                  })}
                </ol>
              </nav>
            )}

            <div className="summaries__reading">
              <section id="summary-book" className="summary-book" aria-labelledby="book-summary-heading" tabIndex={-1}>
                <h2 id="book-summary-heading" className="summary-book__title">
                  {t("summary.wholeBook")}
                </h2>
                <SummaryText text={data.book.summary} />
              </section>

              {data.chapters.length > 0 && (
                <section className="summary-chapters" aria-labelledby="chapter-summaries-heading">
                  <h2 id="chapter-summaries-heading" className="summary-chapters__title">
                    {book.chapters.length ? t("summary.byChapter") : t("summary.bySection")}
                  </h2>
                  <ol className="summary-chapter-list">
                    {data.chapters.map((chapter) => (
                      <li
                        key={chapter.chapter_index}
                        id={`chapter-${chapter.chapter_index}`}
                        className="summary-chapter"
                        tabIndex={-1}
                      >
                        <h3 className="summary-chapter__title">
                          <span className="summary-chapter__number">{chapter.chapter_index + 1}</span>
                          <span className="summary-chapter__name" lang={langOf(chapter.title)}>
                            {chapter.title}
                          </span>
                          <span className="summary-chapter__pages">
                            {formatPages(chapter.start_page, chapter.end_page)}
                          </span>
                        </h3>
                        {chapter.summary ? (
                          <SummaryText text={chapter.summary} />
                        ) : (
                          <p className="muted">{t("summary.chapterEmpty")}</p>
                        )}
                      </li>
                    ))}
                  </ol>
                </section>
              )}
            </div>
          </div>
        </>
      )}

      <ConfirmDialog
        open={confirmRebuild}
        title={t("summary.rebuildTitle", { language: language === "gujarati" ? "Gujarati" : "English" })}
        confirmLabel={t("summary.rebuildConfirm")}
        cancelLabel={t("common.cancel")}
        onCancel={() => setConfirmRebuild(false)}
        onConfirm={() => {
          setConfirmRebuild(false);
          rebuild.mutate();
        }}
      >
        <p>{t("summary.rebuildBody")}</p>
        <p className="muted">{t("summary.introCost")}</p>
      </ConfirmDialog>
    </div>
  );
}

/**
 * Coming from Contents ("…/summaries#chapter-3"): once the summaries are on
 * screen, bring that chapter into view and move focus to it.
 */
function useScrollToHash(ready: boolean) {
  const { hash } = useLocation();
  useEffect(() => {
    if (!ready || !hash) return;
    const target = document.getElementById(decodeURIComponent(hash.slice(1)));
    if (!target) return;
    target.scrollIntoView({ block: "start" });
    target.focus({ preventScroll: true });
  }, [ready, hash]);
}

/** Which section is being read, for the chapter rail. */
function useCurrentSection(ready: boolean, chapterCount: number): string {
  const [current, setCurrent] = useState("summary-book");
  useEffect(() => {
    if (!ready || typeof IntersectionObserver === "undefined") return;
    const sections = [...document.querySelectorAll<HTMLElement>("#summary-book, .summary-chapter")];
    const visible = new Map<string, boolean>();
    const observer = new IntersectionObserver(
      (records) => {
        for (const record of records) visible.set(record.target.id, record.isIntersecting);
        // The first section, in page order, that is in the reading band.
        const first = sections.find((section) => visible.get(section.id));
        if (first) setCurrent(first.id);
      },
      // The reading band: the upper part of the screen, below the sticky tabs.
      { rootMargin: "-20% 0px -55% 0px" },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [ready, chapterCount]);
  return current;
}

/** Summary paragraphs, with the model's lists and short headings kept as such. */
function SummaryText({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let items: ReactNode[] = [];
  const flush = () => {
    if (items.length) out.push(<ul key={`list-${out.length}`} className="summary-text__list">{items}</ul>);
    items = [];
  };
  answerBlocks(text).forEach((block, i) => {
    if (block.kind === "item") {
      items.push(<li key={i}>{block.text}</li>);
      return;
    }
    flush();
    out.push(
      <p key={i} className={block.kind === "heading" ? "text-heading" : undefined}>
        {block.text}
      </p>,
    );
  });
  flush();

  return (
    <div className="summary-text" lang={langOf(text)}>
      {out}
    </div>
  );
}
