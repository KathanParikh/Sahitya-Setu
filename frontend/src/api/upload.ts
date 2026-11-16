/**
 * PDF upload with progress. fetch() cannot report upload progress, so this one
 * request uses XMLHttpRequest, with the same token and error handling as
 * client.ts. It calls the existing POST /api/upload unchanged.
 */
import { config } from "../config";
import { getAccessToken, supabase } from "../auth/supabase";
import { ApiError, errorMessage } from "./client";
import type { UploadResponse } from "./types";

/** The backend's default limit (SS_MAX_UPLOAD_MB). The server enforces its own. */
export const MAX_UPLOAD_MB = 50;

export interface UploadOptions {
  useOcr: boolean;
  /** 0..1 while the file is being sent. */
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
}

export async function uploadPdf(file: File, options: UploadOptions): Promise<UploadResponse> {
  const token = await getAccessToken();
  const url = new URL(`${config.apiUrl}/api/upload`);
  url.searchParams.set("use_ocr", String(options.useOcr));

  const form = new FormData();
  form.append("file", file);

  return new Promise<UploadResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url.toString());
    xhr.setRequestHeader("Accept", "application/json");
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) options.onProgress?.(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error"));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as UploadResponse);
        return;
      }
      if (xhr.status === 401) void supabase?.auth.signOut();
      const retry = Number(xhr.getResponseHeader("Retry-After"));
      reject(
        new ApiError(
          xhr.status,
          errorMessage(body) ?? (xhr.statusText || `HTTP ${xhr.status}`),
          Number.isFinite(retry) && retry > 0 ? retry : null,
        ),
      );
    };

    options.signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(form);
  });
}

/** A reason to refuse the file before sending it, or null. */
export function fileProblem(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf")) return "Only PDF files can be uploaded.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `This file is larger than ${MAX_UPLOAD_MB} MB.`;
  if (file.size === 0) return "This file is empty.";
  return null;
}
