/**
 * A thin fetch wrapper for the FastAPI backend.
 *
 * It attaches the Supabase access token, and turns FastAPI's `{detail}` error
 * bodies into ApiError so screens can show the backend's own message.
 */

export class ApiError extends Error {
  /** HTTP status, or 0 when the server could not be reached. */
  readonly status: number;
  /** Seconds to wait, from Retry-After (sent with 429). */
  readonly retryAfter: number | null;

  constructor(status: number, message: string, retryAfter: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

export interface ApiClientOptions {
  baseUrl: string;
  /** The current access token, or null when signed out. */
  getToken: () => Promise<string | null>;
  /** Called on a 401 so the app can sign out. */
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  /** Plain objects are sent as JSON; FormData is sent as multipart. */
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
}

export type ApiRequest = <T>(path: string, options?: RequestOptions) => Promise<T>;

/** FastAPI sends `detail` as a string, or as a list of validation errors (422). */
export function errorMessage(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : ""))
      .filter(Boolean);
    return messages.length ? messages.join("; ") : null;
  }
  return null;
}

function buildUrl(baseUrl: string, path: string, query?: RequestOptions["query"]): string {
  const url = new URL(baseUrl + path);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
  }
  return url.toString();
}

export function createApiClient(options: ApiClientOptions): ApiRequest {
  const fetchImpl = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args));

  return async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
    const headers = new Headers({ Accept: "application/json" });
    const token = await options.getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    let body: BodyInit | undefined;
    if (init.body instanceof FormData) {
      body = init.body; // the browser sets the multipart boundary
    } else if (init.body !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(init.body);
    }

    let response: Response;
    try {
      response = await fetchImpl(buildUrl(options.baseUrl, path, init.query), {
        method: init.method ?? "GET",
        headers,
        body,
        signal: init.signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, "Network error");
    }

    const text = await response.text();
    let parsed: unknown = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = null;
      }
    }

    if (!response.ok) {
      if (response.status === 401) options.onUnauthorized?.();
      const retry = Number(response.headers.get("Retry-After"));
      throw new ApiError(
        response.status,
        errorMessage(parsed) ?? (response.statusText || `HTTP ${response.status}`),
        Number.isFinite(retry) && retry > 0 ? retry : null,
      );
    }
    return parsed as T;
  };
}
