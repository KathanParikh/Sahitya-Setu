import { missingSettings } from "../config";
import { AuthLayout } from "../components/AuthLayout";
import { t } from "../i18n";

/** Shown instead of the app when required .env.local settings are missing. */
export function SetupPage() {
  return (
    <AuthLayout>
      <div className="auth__form stack">
        <h1 className="auth__title">{t("setup.title")}</h1>
        <p>{t("setup.body")}</p>
        <ul className="setup__list">
          {missingSettings.map((name) => (
            <li key={name}>
              <code>{name}</code>
            </li>
          ))}
        </ul>
        <p className="muted">{t("setup.hint")}</p>
      </div>
    </AuthLayout>
  );
}
