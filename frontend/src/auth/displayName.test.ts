import { describe, expect, it } from "vitest";
import { displayName, initialOf } from "./displayName";

describe("displayName", () => {
  it("prefers a username or display name from Supabase metadata", () => {
    expect(displayName({ email: "a@b.com", user_metadata: { username: "  urvi  " } })).toBe("urvi");
    expect(displayName({ email: "a@b.com", user_metadata: { display_name: "Urvi D" } })).toBe("Urvi D");
    expect(displayName({ email: "a@b.com", user_metadata: { full_name: "Full Name" } })).toBe("Full Name");
  });

  it("falls back to the email prefix when no name is stored", () => {
    expect(displayName({ email: "reader.one@example.com", user_metadata: {} })).toBe("reader.one");
    expect(displayName({ email: "reader@example.com", user_metadata: { username: "   ", email_verified: true } })).toBe("reader");
    expect(displayName({ email: "reader@example.com" })).toBe("reader");
  });

  it("returns an empty string when there is nothing to show", () => {
    expect(displayName(null)).toBe("");
    expect(displayName({ email: null })).toBe("");
  });
});

describe("initialOf", () => {
  it("upper-cases the first character, including Gujarati names", () => {
    expect(initialOf("reader")).toBe("R");
    expect(initialOf("ઉર્વેશ")).toBe("ઉ");
    expect(initialOf("")).toBe("?");
  });
});
