import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { t } from "../i18n";

export function NotFoundPage() {
  return (
    <div className="container page">
      <EmptyState level={1} title={t("notFound.title")} action={<Link to="/">{t("notFound.action")}</Link>}>
        <p>{t("notFound.body")}</p>
      </EmptyState>
    </div>
  );
}
