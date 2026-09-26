# Frontend (React) — next step

Not built yet. The backend API it will consume is running and documented at
<http://localhost:8000/docs>.

What the UI needs to cover:

- **Upload**: `POST /api/upload`, then poll `GET /api/documents/{doc_id}`
  until `status` is `ready`. Show the `progress` string — embedding a full
  book on CPU takes minutes and the user needs to see it moving.
- **Ask**: `POST /api/ask` with `{doc_id, question}`. Render `answer`, and
  render `citations[]` as clickable page references (each has `page_start`,
  `page_end`, `chapter_title`, `snippet`, and `retrieved_by` — whether BM25,
  the vector search, or both found it).
- **Not found**: when `found` is `false`, show the refusal plainly rather than
  as an error. That behaviour is the point of the system.
- **Trace** (optional but worth building for the demo): `trace[]` lists every
  graph node that ran, so the grading and query-rewriting decisions can be
  shown live.
- **Summaries**: `GET /api/summary/{doc_id}` and
  `GET /api/summary/{doc_id}/chapters`.
- **Evaluation**: `GET /api/evaluate/{doc_id}?cached=true` to display the last
  stored RAGAS report.

CORS is already open to `http://localhost:3000` and `http://localhost:5173`
(configurable via `SS_CORS_ORIGINS`).
