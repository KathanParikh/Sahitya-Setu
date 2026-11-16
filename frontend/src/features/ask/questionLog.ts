/**
 * The question log for one book: each question asked and what came back.
 *
 * The backend keeps no question history, so the log lives in this browser
 * (localStorage, per user and book). A question in flight is held in memory and
 * carries on if the reader switches tabs; only settled entries are saved.
 */
import { useCallback, useSyncExternalStore } from "react";
import { ApiError } from "../../api/client";
import { api } from "../../api/endpoints";
import type { AskResponse, Citation, ContentLanguage } from "../../api/types";

/** The parts of an /api/ask response the log shows. */
export interface StoredAnswer {
  answer: string;
  found: boolean;
  citations: Citation[];
  /** Full text of each cited passage; contexts[i] belongs to citations[i]. */
  contexts: string[];
  language: ContentLanguage;
  elapsed_seconds: number;
}

export interface LogEntry {
  id: string;
  question: string;
  askedAt: number;
  status: "pending" | "answered" | "error";
  result?: StoredAnswer;
  error?: { status: number; message: string };
}

const MAX_ENTRIES = 30;
const VERSION = "v1";

const logs = new Map<string, LogEntry[]>();
const listeners = new Map<string, Set<() => void>>();

function storageKey(key: string): string {
  return `ss:questions:${VERSION}:${key}`;
}

function load(key: string): LogEntry[] {
  try {
    const raw = window.localStorage.getItem(storageKey(key));
    const parsed = raw ? (JSON.parse(raw) as LogEntry[]) : [];
    return Array.isArray(parsed) ? parsed.filter((e) => e && e.status !== "pending") : [];
  } catch {
    return [];
  }
}

function save(key: string, entries: LogEntry[]): void {
  let settled = entries.filter((e) => e.status !== "pending").slice(-MAX_ENTRIES);
  // If storage is full, drop the oldest entries until it fits.
  while (settled.length) {
    try {
      window.localStorage.setItem(storageKey(key), JSON.stringify(settled));
      return;
    } catch {
      settled = settled.slice(Math.ceil(settled.length / 4));
    }
  }
  try {
    window.localStorage.removeItem(storageKey(key));
  } catch {
    /* storage unavailable: the log simply is not kept */
  }
}

function get(key: string): LogEntry[] {
  let entries = logs.get(key);
  if (!entries) {
    entries = load(key);
    logs.set(key, entries);
  }
  return entries;
}

function set(key: string, entries: LogEntry[]): void {
  logs.set(key, entries);
  save(key, entries);
  listeners.get(key)?.forEach((notify) => notify());
}

function update(key: string, id: string, patch: Partial<LogEntry>): void {
  set(
    key,
    get(key).map((e) => (e.id === id ? { ...e, ...patch } : e)),
  );
}

function newId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function stored(response: AskResponse): StoredAnswer {
  return {
    answer: response.answer,
    found: response.found,
    citations: response.citations ?? [],
    contexts: response.contexts ?? [],
    language: response.language,
    elapsed_seconds: response.elapsed_seconds,
  };
}

async function run(key: string, docId: string, id: string, question: string): Promise<void> {
  try {
    const response = await api.ask(docId, question);
    update(key, id, { status: "answered", result: stored(response), error: undefined });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : -1;
    const message = error instanceof Error ? error.message : String(error);
    update(key, id, { status: "error", error: { status, message } });
  }
}

/** Remove every saved log for a book (after the book is deleted). */
export function forgetBook(docId: string): void {
  for (const key of [...logs.keys()]) if (key.endsWith(`:${docId}`)) logs.delete(key);
  try {
    const prefix = `ss:questions:${VERSION}:`;
    for (let i = window.localStorage.length - 1; i >= 0; i--) {
      const name = window.localStorage.key(i);
      if (name?.startsWith(prefix) && name.endsWith(`:${docId}`)) window.localStorage.removeItem(name);
    }
  } catch {
    /* nothing saved */
  }
}

/** The log for one user's book, oldest first, with actions. */
export function useQuestionLog(userId: string, docId: string) {
  const key = `${userId}:${docId}`;

  const subscribe = useCallback(
    (notify: () => void) => {
      const set = listeners.get(key) ?? new Set();
      set.add(notify);
      listeners.set(key, set);
      return () => set.delete(notify);
    },
    [key],
  );
  const entries = useSyncExternalStore(subscribe, () => get(key));

  const ask = useCallback(
    (question: string) => {
      const entry: LogEntry = { id: newId(), question, askedAt: Date.now(), status: "pending" };
      set(key, [...get(key), entry]);
      void run(key, docId, entry.id, question);
      return entry.id;
    },
    [key, docId],
  );

  const retry = useCallback(
    (id: string) => {
      const entry = get(key).find((e) => e.id === id);
      if (!entry) return;
      update(key, id, { status: "pending", askedAt: Date.now(), error: undefined });
      void run(key, docId, id, entry.question);
    },
    [key, docId],
  );

  const remove = useCallback((id: string) => set(key, get(key).filter((e) => e.id !== id)), [key]);
  const clear = useCallback(() => set(key, get(key).filter((e) => e.status === "pending")), [key]);

  return { entries, ask, retry, remove, clear, pending: entries.some((e) => e.status === "pending") };
}
