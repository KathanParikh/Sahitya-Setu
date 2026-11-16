/**
 * Reader-facing text for Supabase Auth errors, and the form checks run before
 * anything is sent to Supabase.
 */
import { t } from "../i18n";

/** The parts of a Supabase AuthError the UI uses. */
export interface AuthFailure {
  code?: string;
  message: string;
  status?: number;
}

export interface AuthMessage {
  title: string;
  body?: string;
}

export const MIN_PASSWORD_LENGTH = 8;

export function describeAuthError(error: AuthFailure): AuthMessage {
  switch (error.code) {
    case "invalid_credentials":
      return {
        title: t("authError.invalidCredentials.title"),
        body: t("authError.invalidCredentials.body"),
      };
    case "email_not_confirmed":
      return {
        title: t("authError.emailNotConfirmed.title"),
        body: t("authError.emailNotConfirmed.body"),
      };
    case "user_already_exists":
    case "email_exists":
      return { title: t("authError.userExists.title"), body: t("authError.userExists.body") };
    case "weak_password":
      // Supabase names the rule that failed (length, characters), so show it.
      return { title: t("authError.weakPassword.title"), body: error.message };
    case "signup_disabled":
    case "email_provider_disabled":
      return {
        title: t("authError.signupDisabled.title"),
        body: t("authError.signupDisabled.body"),
      };
    case "over_request_rate_limit":
    case "over_email_send_rate_limit":
      return { title: t("authError.rateLimited.title"), body: t("authError.rateLimited.body") };
  }
  if (error.status === 429) {
    return { title: t("authError.rateLimited.title"), body: t("authError.rateLimited.body") };
  }
  // supabase-js reports a failed fetch as status 0 (AuthRetryableFetchError).
  if (error.status === 0) {
    return { title: t("authError.network.title"), body: t("authError.network.body") };
  }
  return { title: t("authError.generic.title"), body: t("authError.generic.body") };
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function emailProblem(email: string): string | null {
  const value = email.trim();
  if (!value) return t("form.emailRequired");
  if (!EMAIL_PATTERN.test(value)) return t("form.emailInvalid");
  return null;
}

export function signInPasswordProblem(password: string): string | null {
  return password ? null : t("form.passwordRequired");
}

export function newPasswordProblem(password: string): string | null {
  if (!password) return t("form.passwordRequired");
  if (password.length < MIN_PASSWORD_LENGTH) {
    return t("form.passwordTooShort", { min: MIN_PASSWORD_LENGTH });
  }
  return null;
}

export function confirmPasswordProblem(password: string, confirm: string): string | null {
  if (!confirm) return t("form.confirmRequired");
  if (confirm !== password) return t("form.confirmMismatch");
  return null;
}
