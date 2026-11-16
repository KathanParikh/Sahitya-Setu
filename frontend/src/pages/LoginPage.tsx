import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { describeAuthError, emailProblem, signInPasswordProblem, type AuthMessage } from "../auth/authErrors";
import { AuthLayout } from "../components/AuthLayout";
import { Button } from "../components/Button";
import { Notice } from "../components/Notice";
import { PasswordField, TextField } from "../components/TextField";
import { t } from "../i18n";

export function LoginPage() {
  const { session, loading, signIn } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<AuthMessage | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (!loading && session) return <Navigate to={from} replace />;

  // Field errors appear after the first attempt, then update as the user types.
  const emailError = submitted ? emailProblem(email) : null;
  const passwordError = submitted ? signInPasswordProblem(password) : null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    setFailure(null);
    if (emailProblem(email)) return emailRef.current?.focus();
    if (signInPasswordProblem(password)) return passwordRef.current?.focus();

    setSubmitting(true);
    const { error } = await signIn(email.trim(), password);
    setSubmitting(false);
    if (error) {
      setFailure(describeAuthError(error));
      passwordRef.current?.select();
    }
    // On success the session changes and <Navigate> above takes over.
  }

  return (
    <AuthLayout>
      <form className="auth__form" onSubmit={onSubmit} noValidate aria-busy={submitting}>
        <h1 className="auth__title">{t("login.title")}</h1>
        <p className="auth__subtitle">{t("login.subtitle")}</p>

        <div className="auth__fields">
          {failure && (
            <Notice tone="error" title={failure.title}>
              {failure.body}
            </Notice>
          )}
          <TextField
            ref={emailRef}
            label={t("form.email")}
            type="email"
            autoComplete="email"
            inputMode="email"
            autoCapitalize="none"
            spellCheck={false}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={emailError}
            disabled={submitting}
          />
          <PasswordField
            ref={passwordRef}
            label={t("form.password")}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={passwordError}
            disabled={submitting}
          />
          <Button type="submit" variant="primary" block className="auth__submit" disabled={submitting}>
            {submitting && <span className="spinner" aria-hidden="true" />}
            {submitting ? t("login.submitting") : t("login.submit")}
          </Button>
        </div>

        <p className="auth__switch">
          {t("login.noAccount")}{" "}
          <Link to="/signup" state={location.state}>
            {t("login.createAccount")}
          </Link>
        </p>
        <p className="auth__note">{t("form.privacy")}</p>
      </form>
    </AuthLayout>
  );
}
