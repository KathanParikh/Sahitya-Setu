/**
 * Unit tests for the fetch wrapper. `fetch` is replaced inside these tests
 * only; the app itself always talks to the real backend.
 */
import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient, errorMessage } from "./client";

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    new Response(body === undefined ? null : JSON.stringify(body), { status, headers }),
  );
}

function client(fetchImpl: typeof fetch, token: string | null = "tok", onUnauthorized = vi.fn()) {
  return {
    request: createApiClient({
      baseUrl: "http://api.test",
      getToken: async () => token,
      onUnauthorized,
      fetchImpl,
    }),
    onUnauthorized,
  };
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to fail");
}

describe("createApiClient", () => {
  it("sends the access token as a bearer header", async () => {
    const fetchImpl = respond(200, []);
    await client(fetchImpl).request("/api/documents");
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(String(url)).toBe("http://api.test/api/documents");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer tok");
  });

  it("sends no Authorization header when signed out", async () => {
    const fetchImpl = respond(200, {});
    await client(fetchImpl, null).request("/api/health");
    expect(new Headers(fetchImpl.mock.calls[0]![1]?.headers).has("Authorization")).toBe(false);
  });

  it("sends JSON bodies and query parameters", async () => {
    const fetchImpl = respond(200, { answer: "x" });
    await client(fetchImpl).request("/api/ask", {
      method: "POST",
      body: { doc_id: "d1", question: "કોણ?" },
      query: { language: "gujarati", force: undefined },
    });
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(String(url)).toBe("http://api.test/api/ask?language=gujarati");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual({ doc_id: "d1", question: "કોણ?" });
  });

  it("leaves the multipart content type to the browser for uploads", async () => {
    const fetchImpl = respond(200, { doc_id: "d1" });
    const form = new FormData();
    form.append("file", new Blob(["%PDF"]), "book.pdf");
    await client(fetchImpl).request("/api/upload", { method: "POST", body: form });
    const init = fetchImpl.mock.calls[0]![1];
    expect(init?.body).toBe(form);
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
  });

  it("returns the parsed body on success", async () => {
    const data = await client(respond(200, { status: "ok" })).request<{ status: string }>("/x");
    expect(data).toEqual({ status: "ok" });
  });

  it("calls onUnauthorized and raises 401", async () => {
    const { request, onUnauthorized } = client(respond(401, { detail: "Please sign in." }));
    const error = await caught(request("/api/documents"));
    expect(error.status).toBe(401);
    expect(error.message).toBe("Please sign in.");
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("keeps the backend's message for a book that is still processing (409)", async () => {
    const detail = "Document is 'processing' (chunking). Wait for processing to finish.";
    const error = await caught(client(respond(409, { detail })).request("/api/ask"));
    expect(error.status).toBe(409);
    expect(error.message).toBe(detail);
  });

  it("reads Retry-After on a rate limit (429)", async () => {
    const fetchImpl = respond(429, { detail: "Hourly limit reached." }, { "Retry-After": "600" });
    const error = await caught(client(fetchImpl).request("/api/ask"));
    expect(error.status).toBe(429);
    expect(error.retryAfter).toBe(600);
  });

  it("raises 503 when the language model is unavailable", async () => {
    const detail = "The language model could not be reached. Please try again later.";
    const error = await caught(client(respond(503, { detail })).request("/api/ask"));
    expect(error.status).toBe(503);
    expect(error.message).toBe(detail);
  });

  it("falls back to the status text when the body is not JSON", async () => {
    const fetchImpl = vi.fn(async () => new Response("<html>bad gateway</html>", {
      status: 502,
      statusText: "Bad Gateway",
    }));
    const error = await caught(client(fetchImpl).request("/x"));
    expect(error.status).toBe(502);
    expect(error.message).toBe("Bad Gateway");
  });

  it("reports an unreachable server as status 0", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const error = await caught(client(fetchImpl).request("/x"));
    expect(error.status).toBe(0);
    expect(error.isNetworkError).toBe(true);
  });
});

describe("errorMessage", () => {
  it("joins FastAPI validation errors", () => {
    expect(
      errorMessage({ detail: [{ msg: "field required" }, { msg: "too short" }] }),
    ).toBe("field required; too short");
  });

  it("returns null when there is no detail", () => {
    expect(errorMessage({ message: "x" })).toBeNull();
    expect(errorMessage(null)).toBeNull();
  });
});
