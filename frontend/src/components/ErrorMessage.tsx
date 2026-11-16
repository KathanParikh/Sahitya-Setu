import { canRetry, describeError } from "../lib/errors";
import { t } from "../i18n";
import { Button } from "./Button";
import { Notice } from "./Notice";

export { describeError };

/**
 * An error, explained; with Try again when repeating the request could help.
 * With a title, the title says what failed and the explanation follows it.
 */
export function ErrorMessage({ error, onRetry, title }: { error: unknown; onRetry?: () => void; title?: string }) {
  return (
    <Notice tone="error" title={title ?? describeError(error)}>
      {title && <p>{describeError(error)}</p>}
      {onRetry && canRetry(error) && (
        <Button variant="quiet" className="notice__action" onClick={onRetry}>
          {t("common.retry")}
        </Button>
      )}
    </Notice>
  );
}
