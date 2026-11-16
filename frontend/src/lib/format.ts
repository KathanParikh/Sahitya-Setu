/** Formatting for dates, sizes, durations and page ranges (interface language: English). */

const dateFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : dateFormat.format(date);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "45 s", "3 min 05 s" */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${String(s % 60).padStart(2, "0")} s`;
}

/** "p. 12" or "pp. 12–14" */
export function formatPages(start: number, end: number): string {
  return start === end || end < start ? `p. ${start}` : `pp. ${start}–${end}`;
}

export function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString("en-GB")} ${count === 1 ? one : many}`;
}

const timeOfDay = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

/** "Today, 14:05", "Yesterday, 09:12", or "3 Mar 2026". */
export function formatAskedAt(ms: number, now: number = Date.now()): string {
  const date = new Date(ms);
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diff = Math.round((day(new Date(now)) - day(date)) / 86_400_000);
  if (diff === 0) return `Today, ${timeOfDay.format(date)}`;
  if (diff === 1) return `Yesterday, ${timeOfDay.format(date)}`;
  return dateFormat.format(date);
}
