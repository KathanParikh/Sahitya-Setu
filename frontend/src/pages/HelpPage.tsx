import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { MAX_UPLOAD_MB } from "../api/upload";

/**
 * Help & Support: how Sahitya Setu works, what its limits are, and what to do
 * when something fails. Everything here describes the app as it is built.
 */
const SECTIONS: { id: string; title: string; body: ReactNode }[] = [
  {
    id: "upload",
    title: "Adding a book",
    body: (
      <>
        <p>
          Use <strong>Upload PDF</strong> on the library page, or drop a PDF onto it. Files can be up to {MAX_UPLOAD_MB}{" "}
          MB.
        </p>
        <p>
          Before the upload starts you choose how the text is read. <strong>Read scanned pages with OCR</strong> is the
          right choice for most Gujarati books: pages that are images, or that use old non-Unicode Gujarati fonts, are
          read with OCR, and pages with clean text are used as they are. <strong>Use the PDF's text only</strong> is
          faster, but pages without usable text are left out.
        </p>
        <p>
          After the upload the book is processed: its text is read, split into passages and indexed chapter by chapter.
          A full book takes a few minutes. The library shows its progress and updates by itself.
        </p>
      </>
    ),
  },
  {
    id: "ask",
    title: "Asking questions",
    body: (
      <>
        <p>
          Open a book and use the <strong>Ask</strong> tab. Ask in Gujarati or English about characters, events, places
          or ideas. Answers are written only from the book's text, and each statement cites the pages it comes from.
        </p>
        <p>
          Select a page reference in an answer to see the passage it was taken from. If the book does not contain the
          answer, Sahitya Setu says so rather than guessing.
        </p>
        <p>
          <strong>Copy answer</strong> copies the answer with its page references and a list of its sources.
        </p>
      </>
    ),
  },
  {
    id: "history",
    title: "Your question history",
    body: (
      <>
        <p>
          The <strong>History</strong> tab of each book lists the questions you have asked about it. Opening one shows
          the answer and its sources again.
        </p>
        <p>
          History is saved in this browser only, up to 30 questions per book. It is not stored on the server, so it does
          not appear on other devices or browsers, and clearing this browser's site data removes it.
        </p>
      </>
    ),
  },
  {
    id: "summaries",
    title: "Summaries and contents",
    body: (
      <>
        <p>
          The <strong>Summaries</strong> tab gives a summary of the whole book and one for each chapter, in Gujarati or
          English. The first time, they are written for you, which can take several minutes for a long book and counts
          toward an hourly limit. After that they are saved and appear quickly.
        </p>
        <p>
          The server keeps one set of summaries per book. <strong>Rewrite summaries</strong> replaces it, in either
          language.
        </p>
        <p>
          The <strong>Contents</strong> tab lists the chapters found in the book, detected from headings in its text, so
          titles may differ slightly from the printed book.
        </p>
      </>
    ),
  },
  {
    id: "trouble",
    title: "When something goes wrong",
    body: (
      <ul className="help__list">
        <li>
          <strong>“The server could not be reached.”</strong> Check your internet connection. If you run Sahitya Setu
          yourself, check that the backend is running.
        </li>
        <li>
          <strong>A book is “Not processed”.</strong> The reason is shown under its name. Delete it from the library and
          upload it again, with OCR on if it is a scanned book.
        </li>
        <li>
          <strong>Answers or summaries contain odd words.</strong> Text read by OCR can contain recognition errors, and
          these carry into answers.
        </li>
        <li>
          <strong>“Hourly limit reached.”</strong> Questions and summaries have an hourly limit per account. The message
          says how long to wait.
        </li>
        <li>
          <strong>“Your session has ended.”</strong> Sign in again; your books are kept.
        </li>
      </ul>
    ),
  },
  {
    id: "privacy",
    title: "Privacy and support",
    body: (
      <>
        <p>Your books, their summaries and your questions are visible only to you.</p>
        <p>
          If a problem keeps happening, note the exact message shown and the book it concerns, and contact whoever runs
          your Sahitya Setu installation.
        </p>
      </>
    ),
  },
];

export function HelpPage() {
  return (
    <div className="container help view">
      <header className="help__intro">
        <h1 className="page-title">Help &amp; Support</h1>
        <p className="help__lead">
          How Sahitya Setu works, what to expect from it, and what to do when something does not work.
        </p>
      </header>

      <div className="help__layout">
        <nav className="help__toc" aria-label="On this page">
          <ol>
            {SECTIONS.map((section) => (
              <li key={section.id}>
                <a href={`#${section.id}`}>{section.title}</a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="help__body">
          {SECTIONS.map((section) => (
            <section key={section.id} id={section.id} className="help__section" aria-labelledby={`${section.id}-title`}>
              <h2 id={`${section.id}-title`} className="help__title">
                {section.title}
              </h2>
              <div className="help__text">{section.body}</div>
            </section>
          ))}
          <p className="help__back">
            <Link to="/">Back to your library</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
