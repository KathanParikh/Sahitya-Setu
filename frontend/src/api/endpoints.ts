/**
 * One function per existing backend endpoint used by the app.
 * (Uploads go through upload.ts, which reports progress.)
 * Paths and parameters match backend/api/main.py exactly.
 */
import { config } from "../config";
import { getAccessToken, supabase } from "../auth/supabase";
import { createApiClient } from "./client";
import type {
  AskResponse,
  BookDetail,
  BookDocument,
  BookSummary,
  ChapterSummaries,
  ContentLanguage,
  DeleteResponse,
  Health,
} from "./types";

export const request = createApiClient({
  baseUrl: config.apiUrl,
  getToken: getAccessToken,
  // The backend rejected the token (expired, revoked or account deleted).
  onUnauthorized: () => {
    void supabase?.auth.signOut();
  },
});

const enc = encodeURIComponent;

export const api = {
  health: () => request<Health>("/api/health"),

  listDocuments: () => request<BookDocument[]>("/api/documents"),

  getDocument: (docId: string) => request<BookDetail>(`/api/documents/${enc(docId)}`),

  deleteDocument: (docId: string) =>
    request<DeleteResponse>(`/api/documents/${enc(docId)}`, { method: "DELETE" }),

  ask: (docId: string, question: string, signal?: AbortSignal) =>
    request<AskResponse>("/api/ask", {
      method: "POST",
      body: { doc_id: docId, question },
      signal,
    }),

  /**
   * Known backend limitation: the summary cache does not record language, so a
   * cached summary is returned whatever `language` is asked for.
   */
  bookSummary: (docId: string, options: { language?: ContentLanguage; force?: boolean } = {}) =>
    request<BookSummary>(`/api/summary/${enc(docId)}`, {
      query: { language: options.language, force: options.force || undefined },
    }),

  chapterSummaries: (
    docId: string,
    options: { language?: ContentLanguage; force?: boolean } = {},
  ) =>
    request<ChapterSummaries>(`/api/summary/${enc(docId)}/chapters`, {
      query: { language: options.language, force: options.force || undefined },
    }),
};
