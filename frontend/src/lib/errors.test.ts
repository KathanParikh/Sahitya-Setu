import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { canRetry, describeError } from "./errors";

describe("describeError", () => {
  it("explains unreachable servers and ended sessions", () => {
    expect(describeError(new ApiError(0, "Network error"))).toMatch(/could not be reached/);
    expect(describeError(new ApiError(401, "Please sign in."))).toMatch(/session has ended/);
  });

  it("replaces the backend's internal 404 and 409 wording", () => {
    expect(describeError(new ApiError(404, "Unknown document 'abc'."))).toMatch(/no longer in your library/);
    expect(describeError(new ApiError(409, "Document is 'processing' ()."))).toMatch(/still being processed/);
  });

  it("shows reader-facing backend details as sent", () => {
    const limit = "Hourly limit reached. Please try again in about 12 minutes.";
    expect(describeError(new ApiError(429, limit))).toBe(limit);
    expect(describeError(new ApiError(503, "The language model could not be reached. Please try again later."))).toMatch(
      /language model/,
    );
  });

  it("explains bare HTTP reason phrases by status", () => {
    expect(describeError(new ApiError(502, "Bad Gateway"))).toMatch(/too long to respond/);
    expect(describeError(new ApiError(500, "Internal Server Error"))).toMatch(/server ran into a problem/);
    expect(describeError(new ApiError(429, "Too Many Requests"))).toMatch(/Too many requests/);
    expect(describeError(new ApiError(413, "HTTP 413"))).toMatch(/too large/);
  });

  it("falls back for errors that are not API errors", () => {
    expect(describeError(new Error("boom"))).toMatch(/did not work/);
  });
});

describe("canRetry", () => {
  it("allows retrying network, server and rate-limit failures only", () => {
    expect(canRetry(new ApiError(0, ""))).toBe(true);
    expect(canRetry(new ApiError(500, ""))).toBe(true);
    expect(canRetry(new ApiError(429, ""))).toBe(true);
    expect(canRetry(new ApiError(404, ""))).toBe(false);
    expect(canRetry(new ApiError(400, ""))).toBe(false);
  });
});
