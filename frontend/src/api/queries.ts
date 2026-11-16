/** React Query hooks over the existing endpoints. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { forgetBook } from "../features/ask/questionLog";
import { api } from "./endpoints";
import type { BookDetail, BookDocument } from "./types";

export const keys = {
  documents: ["documents"] as const,
  document: (docId: string) => ["documents", docId] as const,
  summary: (docId: string, language: string) => ["summary", docId, language] as const,
  chapterSummaries: (docId: string, language: string) => ["chapter-summaries", docId, language] as const,
};

/** Ingestion runs on the server after upload; the client polls until it settles. */
export const POLL_MS = 3000;

export function isBusy(status: BookDocument["status"]): boolean {
  return status === "pending" || status === "processing";
}

export function useDocuments() {
  return useQuery({
    queryKey: keys.documents,
    queryFn: api.listDocuments,
    refetchInterval: (query) =>
      query.state.data?.some((d) => isBusy(d.status)) ? POLL_MS : false,
  });
}

export function useDocument(docId: string) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: keys.document(docId),
    queryFn: async (): Promise<BookDetail> => {
      const detail = await api.getDocument(docId);
      // Keep the library list in step with what this page has seen.
      queryClient.setQueryData<BookDocument[]>(keys.documents, (list) =>
        list?.map((d) => (d.doc_id === docId ? { ...d, ...detail } : d)),
      );
      return detail;
    },
    refetchInterval: (query) => (query.state.data && isBusy(query.state.data.status) ? POLL_MS : false),
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (docId: string) => api.deleteDocument(docId),
    onSuccess: (_result, docId) => {
      queryClient.setQueryData<BookDocument[]>(keys.documents, (list) =>
        list?.filter((d) => d.doc_id !== docId),
      );
      queryClient.removeQueries({ queryKey: keys.document(docId) });
      queryClient.removeQueries({ queryKey: ["summary", docId] });
      queryClient.removeQueries({ queryKey: ["chapter-summaries", docId] });
      forgetBook(docId);
    },
  });
}

/**
 * A book's display title: its PDF title, else its file name without ".pdf"
 * and with "_" and "-" read as spaces ("gujarati_test_book" -> "gujarati test book"),
 * so it can wrap on a cover. The backend falls back to the file name's stem as
 * the title, so a title equal to that stem is treated the same way. The file
 * name itself is shown in Contents.
 */
export function bookTitle(book: Pick<BookDocument, "title" | "filename">): string {
  const stem = book.filename.replace(/\.pdf$/i, "");
  const title = book.title?.trim();
  if (title && title !== stem) return title;
  return stem.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim() || book.filename;
}
