import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import {
  MIN_PASSWORD_LENGTH,
  confirmPasswordProblem,
  describeAuthError,
  emailProblem,
  newPasswordProblem,
  type AuthMessage,
} from "../auth/authErrors";
import { AuthLayout } from "../components/AuthLayout";
import { Button } from "../components/Button";
import { Notice } from "../components/Notice";
import { PasswordField, TextField } from "../components/TextField";
import { t } from "../i18n";

export function SignUpPage() {
  const { session, loading, signUp } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<AuthMessage | null>(null);
  /** Set when Supabase wants the email confirmed before the first sign-in. */
  const [sentTo, setSentTo] = useState<string | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);

  // With email confirmation off, sign-up returns a session: go straight in.
  if (!loading && session) return <Navigate to="/" replace />;

  const emailError = submitted ? emailProblem(email) : null;
  const passwordError = submitted ? newPasswordProblem(password) : null;
  const confirmError = submitted ? confirmPasswordProblem(password, confirm) : null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    setFailure(null);
    if (emailProblem(email)) return emailRef.current?.focus();
    if (newPasswordProblem(password)) return passwordRef.current?.focus();
    if (confirmPasswordProblem(password, confirm)) return confirmRef.current?.focus();

    setSubmitting(true);
    const { error, needsConfirmation } = await signUp(email.trim(), password);
    setSubmitting(false);
    if (error) {
      setFailure(describeAuthError(error));
      return;
    }
    if (needsConfirmation) setSentTo(email.trim());
  }

  if (sentTo) {
    return (
      <AuthLayout>
        <div className="auth__form auth__done">
          <svg className="auth__done-icon" width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <rect x="5" y="9" width="30" height="22" rx="2" stroke="currentColor" strokeWidth="1.5" />
            <path d="M6 11l14 11 14-11" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          </svg>
          <h1 className="auth__title">{t("signup.checkEmailTitle")}</h1>
          <p>{t("signup.checkEmailBody", { email: sentTo })}</p>
          <p className="muted">{t("signup.checkEmailHint")}</p>
          <p className="auth__switch">
            <Link to="/login">{t("signup.backToSignIn")}</Link>
          </p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <form className="auth__form" onSubmit={onSubmit} noValidate aria-busy={submitting}>
        <h1 className="auth__title">{t("signup.title")}</h1>
        <p className="auth__subtitle">{t("signup.subtitle")}</p>

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
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            hint={t("form.passwordHint", { min: MIN_PASSWORD_LENGTH })}
            error={passwordError}
            disabled={submitting}
          />
          <PasswordField
            ref={confirmRef}
            label={t("form.confirmPassword")}
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            error={confirmError}
            disabled={submitting}
          />
          <Button type="submit" variant="primary" block className="auth__submit" disabled={submitting}>
            {submitting && <span className="spinner" aria-hidden="true" />}
            {submitting ? t("signup.submitting") : t("signup.submit")}
          </Button>
        </div>

        <p className="auth__switch">
          {t("signup.haveAccount")}{" "}
          <Link to="/login" state={location.state}>
            {t("signup.signIn")}
          </Link>
        </p>
        <p className="auth__note">{t("form.privacy")}</p>
      </form>
    </AuthLayout>
  );
}
