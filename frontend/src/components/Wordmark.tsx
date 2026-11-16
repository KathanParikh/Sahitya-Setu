import { Link } from "react-router-dom";
import { t } from "../i18n";

interface WordmarkProps {
  /** Render as a link to the library. */
  to?: string;
  size?: "default" | "large";
}

/** The logo: the name "Sahitya Setu" set in the serif (Newsreader), and nothing else. */
export function Wordmark({ to, size = "default" }: WordmarkProps) {
  const className = size === "large" ? "wordmark wordmark--large" : "wordmark";
  return to ? (
    <Link to={to} className={className}>
      {t("app.name")}
    </Link>
  ) : (
    <span className={className}>{t("app.name")}</span>
  );
}
