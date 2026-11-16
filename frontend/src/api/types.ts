/**
 * Response shapes of the existing FastAPI backend (backend/api/main.py),
 * as it returns them today. Keep in sync with the backend; do not add fields
 * the backend does not send.
 */

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

/** A row of the documents table (GET /api/documents, GET /api/documents/{id}). */
export interface BookDocument {
  doc_id: string;
  user_id: string | null;
  filename: string;
  title: string | null;
  author: string | null;
  page_count: number;
  chunk_count: number;
  chapter_count: number;
  status: DocumentStatus;
  /** Human-readable step during ingestion, e.g. "embedding 412 chunks …". */
  progress: string | null;
  /** Reader-facing reason when status is "failed". */
  error: string | null;
  file_path: string | null;
  extraction_stats: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Chapter {
  chapter_index: number;
  title: string;
  start_page: number;
  end_page: number;
}

export interface SampleChunk {
  chunk_id: string;
  text: string;
  page_start: number | null;
  page_end: number | null;
  chapter_title: string | null;
  token_count: number | null;
}

/** GET /api/documents/{id} adds the chapter list (and optional samples). */
export interface BookDetail extends BookDocument {
  chapters: Chapter[];
  chapters_found: string[];
  sample_chunks?: SampleChunk[];
}

/** POST /api/upload */
export interface UploadResponse {
  doc_id: string;
  status: DocumentStatus;
  filename: string;
  message: string;
  pages?: number | null;
  chunks?: number | null;
  chapters_found?: string[] | null;
  sample_chunks?: SampleChunk[] | null;
}

export interface DeleteResponse {
  doc_id: string;
  status: "deleted";
}

export type RetrievalSource = "bm25" | "vector";

/** One retrieved passage the answer was generated from. */
export interface Citation {
  chunk_id: string;
  page_start: number;
  page_end: number;
  chapter_index: number;
  chapter_title: string;
  /** e.g. "પાનું 12 | chapter title" */
  label: string;
  /** First 300 characters of the passage. */
  snippet: string;
  retrieved_by: RetrievalSource[];
}

export interface RetrievedChunk {
  chunk_id: string;
  text: string;
  page_start: number;
  page_end: number;
  chapter_index: number;
  chapter_title: string;
  rrf_score: number;
  bm25_rank: number | null;
  vector_rank: number | null;
  sources: RetrievalSource[];
}

export interface TraceEntry {
  node: string;
  t: number;
  [field: string]: unknown;
}

export type ContentLanguage = "gujarati" | "english";

/** POST /api/ask */
export interface AskResponse {
  doc_id: string;
  question: string;
  /** Answer text with inline page citations, e.g. "(પાનું ૪૨)" or "(page 42)". */
  answer: string;
  /** false means the book does not contain the answer — a refusal, not an error. */
  found: boolean;
  llm_error: string;
  citations: Citation[];
  language: ContentLanguage;
  rewrites_used: number;
  queries_tried: string[];
  contexts: string[];
  retrieved: RetrievedChunk[];
  trace: TraceEntry[];
  elapsed_seconds: number;
}

/** GET /api/summary/{id} */
export interface BookSummary {
  doc_id: string;
  summary: string;
  cached: boolean;
  built_from_chapters?: number;
}

export interface ChapterSummary extends Chapter {
  summary: string;
  cached: boolean;
}

/** GET /api/summary/{id}/chapters */
export interface ChapterSummaries {
  doc_id: string;
  chapter_count: number;
  chapters: ChapterSummary[];
}

/** GET /api/health (no sign-in needed) */
export interface Health {
  status: string;
  llm_provider: string;
  llm_model: string;
  embedding_model: string;
  gemini_key_set: boolean;
  groq_key_set: boolean;
}
