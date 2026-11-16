import { useEffect, useState } from "react";
import { formatDuration } from "../lib/format";

/** A thin determinate bar, or an indeterminate one when `value` is null. */
export function ProgressBar({ value, label }: { value: number | null; label: string }) {
  const percent = value === null ? undefined : Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div
      className={value === null ? "progress progress--indeterminate" : "progress"}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div className="progress__bar" style={percent === undefined ? undefined : { width: `${percent}%` }} />
    </div>
  );
}

/** Seconds since `since` (ms timestamp), updated every second. */
export function useElapsed(since: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (since === null) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [since]);
  return since === null ? 0 : Math.max(0, (now - since) / 1000);
}

/** "1 min 04 s" since `since`, ticking. */
export function Elapsed({ since }: { since: number }) {
  const seconds = useElapsed(since);
  return <span className="elapsed">{formatDuration(seconds)}</span>;
}
