import { describe, expect, it } from "vitest";
import {
  confirmPasswordProblem,
  describeAuthError,
  emailProblem,
  newPasswordProblem,
  signInPasswordProblem,
} from "./authErrors";

describe("describeAuthError", () => {
  it("explains wrong credentials without Supabase's wording", () => {
    const text = describeAuthError({ code: "invalid_credentials", message: "Invalid login credentials", status: 400 });
    expect(text.title).toBe("Email or password is incorrect.");
  });

  it("tells an unconfirmed user to open the confirmation link", () => {
    const text = describeAuthError({ code: "email_not_confirmed", message: "Email not confirmed", status: 400 });
    expect(text.body).toMatch(/confirmation link/);
  });

  it("suggests signing in when the account exists", () => {
    for (const code of ["user_already_exists", "email_exists"]) {
      expect(describeAuthError({ code, message: "x", status: 422 }).title).toMatch(/already exists/);
    }
  });

  it("passes on the password rule Supabase names", () => {
    const message = "Password should be at least 10 characters.";
    expect(describeAuthError({ code: "weak_password", message, status: 422 }).body).toBe(message);
  });

  it("reports rate limits, by code or by status", () => {
    expect(describeAuthError({ code: "over_email_send_rate_limit", message: "x", status: 429 }).title)
      .toBe("Too many attempts.");
    expect(describeAuthError({ message: "x", status: 429 }).title).toBe("Too many attempts.");
  });

  it("reports an unreachable service as a connection problem", () => {
    expect(describeAuthError({ message: "Failed to fetch", status: 0 }).title)
      .toMatch(/Could not reach/);
  });

  it("falls back to a generic message for anything else", () => {
    expect(describeAuthError({ code: "unexpected_failure", message: "db down", status: 500 }).title)
      .toBe("Something went wrong.");
  });
});

describe("form checks", () => {
  it("requires a well-formed email", () => {
    expect(emailProblem("")).toMatch(/Enter your email/);
    expect(emailProblem("reader@")).toMatch(/valid email/);
    expect(emailProblem("  reader@example.com ")).toBeNull();
  });

  it("only requires some password to sign in", () => {
    expect(signInPasswordProblem("")).not.toBeNull();
    expect(signInPasswordProblem("x")).toBeNull();
  });

  it("requires at least 8 characters for a new password", () => {
    expect(newPasswordProblem("1234567")).toMatch(/at least 8/);
    expect(newPasswordProblem("12345678")).toBeNull();
  });

  it("requires the confirmation to match", () => {
    expect(confirmPasswordProblem("abcdefgh", "")).toMatch(/again/);
    expect(confirmPasswordProblem("abcdefgh", "abcdefgx")).toMatch(/do not match/);
    expect(confirmPasswordProblem("abcdefgh", "abcdefgh")).toBeNull();
  });
});
