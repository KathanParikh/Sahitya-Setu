# Sahitya Setu — frontend

React + Vite + TypeScript client for the FastAPI backend in `../backend`.
It uses the backend's existing endpoints unchanged (documented at
<http://localhost:8000/docs> while the backend is running).

## Setup

Requires Node 20 or newer.

```bash
cd frontend
npm install
cp .env.example .env.local   # then fill it in
npm run dev                  # http://localhost:5173
```

`.env.local`:

| Setting | Value |
|---|---|
| `VITE_API_URL` | The backend, default `http://localhost:8000` |
| `VITE_SUPABASE_URL` | Supabase → Project Settings → API → Project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase → Project Settings → API → anon / publishable key |

Use the **anon / publishable** key only. The secret (service role) key belongs
to the backend and must never be put in the frontend.

The dev server runs on port 5173, which the backend already allows
(`SS_CORS_ORIGINS`). If any setting is missing the app shows a setup screen
naming it.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run typecheck` | TypeScript check, no output files |
| `npm test` | Unit tests (Vitest) |
| `npm run build` | Type check and production build into `dist/` |
| `npm run preview` | Serve the production build locally |

## Structure

```
src/
  api/         fetch wrapper, endpoint functions, upload with progress,
               React Query hooks, response types
  auth/        Supabase client, session provider, route guard, auth errors
  components/  app shell and shared components (dialog, notice, fields…)
  features/
    library/   book rows and upload control
    book/      contents tab
    ask/       question form, question log store, answers, sources
    summary/   summaries tab
  i18n/        interface text (en.ts) and the t() helper
  lib/         Gujarati/English text helpers, formatting
  pages/       one component per route
  styles/      tokens.css, global.css and one stylesheet per area
```

- **Routes:** `/login` and `/signup` are public. Signed in:

  | Route | Screen | Backend calls |
  |---|---|---|
  | `/` | Library: books, upload, delete | `GET /api/documents` (polled every 3 s while a book is processing), `POST /api/upload`, `DELETE /api/documents/{id}` |
  | `/books/:id` | Ask: question box and recent questions | `GET /api/documents/{id}`, `POST /api/ask` |
  | `/books/:id/history` | Every saved question for the book | none (read from this browser) |
  | `/books/:id/questions/:entryId` | One saved question: answer, citations, passages | none (read from this browser) |
  | `/help` | Help & Support | none |
  | `/books/:id/summaries` | Book and chapter summaries | `GET /api/summary/{id}`, `GET /api/summary/{id}/chapters` |
  | `/books/:id/contents` | Chapters found in the book | `GET /api/documents/{id}` |

  Signed-out visitors are sent to `/login` and returned afterwards.
- **Layout:** signed-in pages share a slim top bar: a menu button and the
  "Sahitya Setu" wordmark. Uploading starts from the library page or from
  "Upload a book" in the sidebar. The menu opens
  a sidebar over the page (avatar initial, email and account date from
  Supabase; My Library; Upload a book; Help & Support; Log out). The library
  page is one centred column: a short introduction, an upload area (also a
  drop target for a PDF), and the books as a document-style list (name and
  author, date uploaded, status while processing or if it failed; search and
  newest/A–Z order in the browser). A book opens with four
  tabs: **Ask** (a question box, then starter questions or the latest
  questions), **History** (every saved question, with a filter), **Summaries**
  and **Contents**. Each question opens its own page
  (`/books/:id/questions/:entryId`) with the answer, its page citations, the
  cited passages and **Copy answer**, which copies the answer with its page
  references and a list of its sources. `/help` explains the app.
- **Question history:** the backend keeps none, so questions and their
  answers (with citations and passage text) are saved in the browser's
  localStorage, per account and book, up to 30 per book. They are not
  shared between browsers or devices.
- **Upload:** choosing or dropping a PDF does not send it straight away. The
  reader first picks how its text is read, for that upload only: OCR where
  needed (the default; `use_ocr=true`, which OCRs only pages without usable
  text, including legacy-font pages) or the PDF's text only (`use_ocr=false`).
- **Auth:** sign-in and self-registration use Supabase email + password in
  the browser (`signInWithPassword`, `signUp`); no profile record is needed. Each API
  request carries the Supabase access token; the backend verifies it and only
  returns the user's own books. A 401 from the backend signs the user out.
- **Interface language:** English. All labels are in `src/i18n/en.ts`; a
  Gujarati interface can be added as `gu.ts` with the same keys. Book content,
  questions and answers may be Gujarati or English and are marked with the
  matching `lang` attribute where they are shown.
- **Design:** light only: warm white, charcoal and muted teal. Warm white
  (#FAFAF7) page, white surfaces, pale teal for selection and quiet fills,
  muted teal (#39796F) for actions and accents, deep charcoal text; a muted
  red only for errors and deleting. Two type voices,
  each a Latin face paired with a Gujarati one: the serif (Newsreader + Noto
  Serif Gujarati) sets page headings, book and chapter titles and the book's
  own passages; the sans (Instrument Sans + Noto Sans Gujarati) sets the
  interface, questions, answers and summaries. All values are tokens in
  `src/styles/tokens.css`.

## Registration and email confirmation

Self-registration needs no backend change: the backend accepts any valid
Supabase user token, and books are owned by `auth.users.id`.

The sign-up screen handles both Supabase settings:

- **Confirmation off** (the project's setting on 2026-11-13: `mailer_autoconfirm`
  is true): the new user is signed in straight away.
- **Confirmation on:** the user sees "Check your email". To turn it on, in the
  Supabase dashboard:
  1. Authentication → Sign In / Providers → Email → enable *Confirm email*.
  2. Authentication → URL Configuration → add `http://localhost:5173/` (and the
     production address) to *Redirect URLs*. The confirmation link returns to
     the app's origin.
  3. Configure custom SMTP. Supabase's built-in sender allows only a few
     emails per hour and is meant for testing.

Not built yet: forgot-password and display names.

## Known backend limitations

These need backend changes, which are out of scope for the frontend work.
The UI works around them rather than replacing them with mock data.

- **No page-text endpoint.** The backend stores each page's text but has no
  route that returns it. A citation can show the passage snippet from
  `/api/ask` (`citations[].snippet`, first 300 characters), but not the full
  page with the supporting passage highlighted.
- **Summary cache ignores language.** `/api/summary/...?language=` only affects
  a summary being built. Once one is cached, it is returned for both Gujarati
  and English requests. The UI detects the script of the returned text and,
  when it does not match the chosen language, says so and offers "Rewrite
  summaries" (`force=true`), which replaces the saved summary for both.
- **No question history on the server.** Asked questions and answers are kept
  in the browser only (localStorage, per user and book, last 30), so they are
  not shared between devices.
- **No way to check for a saved summary without building one.**
  `GET /api/summary/{id}` writes a summary if none is saved, which takes
  minutes and counts toward the hourly limit. The Summaries tab therefore
  loads automatically only when this browser has loaded that book's summary
  before; otherwise it waits for "Show summaries".
- **Citations point at passages, not exact pages.** `citations[]` gives each
  passage's page range; the answer text carries the exact page, e.g.
  "(પાનું 3)". Clicking a page reference marks the passages whose range
  contains that page. Full passage text comes from `contexts[]`, which is in
  the same order as `citations[]`.
- **Open registration and the shared LLM quota.** Hourly limits are per user
  and held in server memory, so many accounts multiply them. Uploads (5 per
  hour, up to 50 MB each) also count against the Supabase free-tier storage.
- **Evaluation** (`/api/evaluate`) is deliberately not shown in the v1 interface.
