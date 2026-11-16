import { Link } from "react-router-dom";
import { useBook } from "../../pages/BookPage";
import { formatPages } from "../../lib/format";
import { langOf } from "../../lib/text";
import { t } from "../../i18n";

/** More chapters than this, and the contents is set in two columns. */
const SPLIT_AFTER = 6;

/**
 * The book's contents, set like a printed contents page (chapter, dotted
 * leader, pages; each chapter opens its summary). A long one is split
 * into two columns, first half on the left, second half on the right.
 */
export function ContentsTab() {
  const book = useBook();
  const chapters = book.chapters;
  // A long contents splits into two columns; a short one stays in one.
  const split = chapters.length > SPLIT_AFTER;
  const middle = Math.ceil(chapters.length / 2);
  const halves = split ? [chapters.slice(0, middle), chapters.slice(middle)] : [chapters];

  return (
    <div className="contents">
      <section className="contents__chapters" aria-labelledby="chapters-heading">
        <h2 id="chapters-heading" className="contents__heading">
          {t("contents.chapters")}
        </h2>
        {book.chapters.length === 0 ? (
          <div className="state state--inline">
            <p className="state__title">{t("contents.noChaptersTitle")}</p>
            <p className="state__body">{t("contents.noChapters")}</p>
          </div>
        ) : (
          <div className={`toc-columns${halves.length > 1 ? " toc-columns--two" : ""}`}>
            {halves.map((half, i) => (
              // Two lists side by side: the first half of the chapters on the
              // left, the rest on the right. `start` keeps the numbering going.
              <ol key={i} className="toc" start={half[0]!.chapter_index + 1}>
                {half.map((chapter) => (
                  <li key={chapter.chapter_index} className="toc__item">
                    <Link
                      to={`../summaries#chapter-${chapter.chapter_index}`}
                      relative="path"
                      className="toc__link"
                      aria-label={t("contents.openSummary", { title: chapter.title })}
                    >
                      <span className="toc__number">{chapter.chapter_index + 1}</span>
                      <span className="toc__title" lang={langOf(chapter.title)}>
                        {chapter.title}
                      </span>
                      <span className="toc__leader" aria-hidden="true" />
                      <span className="toc__pages">{formatPages(chapter.start_page, chapter.end_page)}</span>
                    </Link>
                  </li>
                ))}
              </ol>
            ))}
          </div>
        )}
        <p className="contents__note">{t("contents.detectedNote")}</p>
      </section>
    </div>
  );
}
