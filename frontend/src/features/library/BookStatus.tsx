import { isBusy } from "../../api/queries";
import { ProgressBar } from "../../components/Progress";
import type { BookDocument } from "../../api/types";
import { t } from "../../i18n";

/**
 * What is happening to a book that cannot be opened yet: being read (with the
 * current step) or not processed (with the reason). Ready books need no label.
 */
export function BookStatus({ book }: { book: BookDocument }) {
  if (isBusy(book.status)) {
    return (
      <div className="book-status book-status--busy" aria-live="polite">
        <p className="book-status__line">
          <span className="spinner" aria-hidden="true" />
          <span>
            <span className="book-status__label">{t("library.processing")}</span>{" "}
            <span className="book-status__detail">{book.progress || t("book.processingQueued")}</span>
          </span>
        </p>
        <ProgressBar value={null} label={t("book.processingTitle")} />
      </div>
    );
  }
  if (book.status === "failed") {
    return (
      <p className="book-status book-status--failed">
        <span>
          <span className="book-status__label">{t("library.failed")}.</span>{" "}
          <span className="book-status__detail">{book.error || t("library.failedGeneric")}</span>
        </span>
      </p>
    );
  }
  return null;
}
