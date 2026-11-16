import type { ReactNode } from "react";
import { t } from "../i18n";
import { LetterField, ReadingJourney } from "./Visuals";
import { Wordmark } from "./Wordmark";

/**
 * Sign-in, sign-up and setup. On the tinted side, the wordmark, what
 * Sahitya Setu is for, and the reading journey (a book page organised into
 * chapters, a question, an answer and a summary) over a faint field of
 * Gujarati letters; the form on the other. On narrow screens the
 * introduction becomes a band above the form, without the picture.
 */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth">
      <section className="auth__intro" aria-label={t("app.name")}>
        <LetterField className="auth__letters" />
        <Wordmark size="large" />

        <div className="auth__intro-body">
          <h2 className="auth__headline">{t("intro.headline")}</h2>
          <p className="auth__lead">{t("intro.lead")}</p>
          <ReadingJourney className="auth__journey" />
        </div>

        <p className="auth__foot">{t("intro.foot")}</p>
      </section>

      <main className="auth__panel">{children}</main>
    </div>
  );
}
