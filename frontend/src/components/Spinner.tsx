/** A small indeterminate spinner with a visible or screen-reader-only label. */
export function Spinner({ label, showLabel = true }: { label: string; showLabel?: boolean }) {
  return (
    <span className="spinner-row" role="status">
      <span className="spinner" aria-hidden="true" />
      <span className={showLabel ? "muted" : "visually-hidden"}>{label}</span>
    </span>
  );
}
