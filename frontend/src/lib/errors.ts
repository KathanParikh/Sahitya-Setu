/**
 * Reader-facing explanations for failed requests.
 *
 * The backend writes most of its error details for readers ("Hourly limit
 * reached. Please try again in about 12 minutes."), and those are shown as
 * sent. A few are internal ("Unknown document 'abc'."), and a failure without
 * a detail only carries the HTTP reason phrase ("Bad Gateway"); those get a
 * plain explanation of what happened and what to do.
 */
import { ApiError } from "../api/client";
import { t } from "../i18n";

/** A backend detail written as a sentence, rather than a bare HTTP reason phrase. */
function isSentence(message: string): boolean {
  return /[.!?।]$/.test(message.trim());
}

export function describeError(error: unknown): string {
  if (!(error instanceof ApiError)) return t("error.generic");
  const { status, message } = error;

  if (error.isNetworkError) return t("error.network");
  if (status === 401) return t("error.unauthorized");
  // Internal wording on these two; say what they mean for the reader.
  if (status === 404) return t("error.bookMissing");
  if (status === 409) return t("error.notReady");
  if (message && isSentence(message)) return message;

  if (status === 400 || status === 422) return t("error.rejected");
  if (status === 413) return t("error.tooLarge");
  if (status === 429) return t("error.rateLimited");
  if (status === 502 || status === 504) return t("error.timeout");
  if (status === 503) return t("error.unavailable");
  if (status >= 500) return t("error.server");
  return t("error.generic");
}

/** Whether trying the same request again could succeed. */
export function canRetry(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.isNetworkError || error.status >= 500 || error.status === 429;
}
