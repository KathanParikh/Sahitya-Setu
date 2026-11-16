import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { keys } from "../../api/queries";
import { fileProblem, uploadPdf } from "../../api/upload";
import type { BookDocument } from "../../api/types";
import { Button } from "../../components/Button";
import { describeError } from "../../components/ErrorMessage";
import { Notice } from "../../components/Notice";
import { ProgressBar } from "../../components/Progress";
import { formatBytes } from "../../lib/format";
import { langOf } from "../../lib/text";
import { t } from "../../i18n";

/**
 * idle → chosen (the reader picks how the PDF is read) → uploading → idle.
 * A file that cannot be sent, or a failed upload, ends in error.
 */
type UploadState =
  | { phase: "idle" }
  | { phase: "chosen"; file: File }
  | { phase: "uploading"; file: File; progress: number }
  | { phase: "error"; file: File | null; message: string };

/** State and actions shared by the upload button, the drop zone and the panel. */
export function useUploader() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<UploadState>({ phase: "idle" });
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  /** Hold a file until the reader confirms the upload, or explain why it cannot go. */
  function choose(file: File) {
    const problem = fileProblem(file);
    setState(problem ? { phase: "error", file, message: problem } : { phase: "chosen", file });
  }

  async function upload(useOcr: boolean) {
    if (state.phase !== "chosen") return;
    const { file } = state;
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ phase: "uploading", file, progress: 0 });
    try {
      const response = await uploadPdf(file, {
        useOcr,
        signal: controller.signal,
        onProgress: (progress) =>
          setState((s) => (s.phase === "uploading" ? { ...s, progress } : s)),
      });
      // Show the new book at once; the list query then polls its progress.
      queryClient.setQueryData<BookDocument[]>(keys.documents, (list) => {
        if (!list || list.some((d) => d.doc_id === response.doc_id)) return list;
        const now = new Date().toISOString();
        const placeholder: BookDocument = {
          doc_id: response.doc_id,
          user_id: null,
          filename: response.filename,
          title: null,
          author: null,
          page_count: 0,
          chunk_count: 0,
          chapter_count: 0,
          status: response.status,
          progress: null,
          error: null,
          file_path: null,
          extraction_stats: {},
          created_at: now,
          updated_at: now,
        };
        return [placeholder, ...list];
      });
      void queryClient.invalidateQueries({ queryKey: keys.documents });
      setState({ phase: "idle" });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setState({ phase: "idle" });
        return;
      }
      setState({ phase: "error", file, message: describeError(error) });
    } finally {
      abortRef.current = null;
    }
  }

  return {
    state,
    inputRef,
    /** Open the file picker. */
    pick: () => inputRef.current?.click(),
    choose,
    upload,
    cancel: () => abortRef.current?.abort(),
    dismiss: () => setState({ phase: "idle" }),
    busy: state.phase === "uploading",
  };
}

export type Uploader = ReturnType<typeof useUploader>;

const UploaderContext = createContext<Uploader | null>(null);

/**
 * One uploader for the signed-in app, so the sidebar's "Upload PDF" works from
 * any page and an upload carries on while the reader moves between pages.
 * Also renders the hidden file input.
 */
export function UploaderProvider({ children }: { children: ReactNode }) {
  const uploader = useUploader();
  return (
    <UploaderContext.Provider value={uploader}>
      {children}
      <UploadInput uploader={uploader} />
    </UploaderContext.Provider>
  );
}

export function useSharedUploader(): Uploader {
  const uploader = useContext(UploaderContext);
  if (!uploader) throw new Error("useSharedUploader must be used inside <UploaderProvider>");
  return uploader;
}

/** The hidden file input behind every "Upload PDF" button. */
function UploadInput({ uploader }: { uploader: Uploader }) {
  return (
    <input
      ref={uploader.inputRef}
      type="file"
      accept="application/pdf,.pdf"
      className="visually-hidden"
      tabIndex={-1}
      aria-hidden="true"
      onChange={(e) => {
        const file = e.target.files?.[0];
        e.target.value = ""; // allow choosing the same file again
        if (file) uploader.choose(file);
      }}
    />
  );
}

export function UploadButton({ uploader }: { uploader: Uploader }) {
  return (
    <Button variant="primary" onClick={uploader.pick} disabled={uploader.busy}>
      <UploadIcon />
      {t("upload.button")}
    </Button>
  );
}

export function UploadIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 13V3.5M6 7.25l4-4 4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3.75 12.5v3.75h12.5V12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The chosen file with its reading option, the upload's progress, or why it failed. */
export function UploadPanel({ uploader }: { uploader: Uploader }) {
  const { state } = uploader;
  if (state.phase === "chosen") return <ChosenFile key={fileKey(state.file)} file={state.file} uploader={uploader} />;

  if (state.phase === "uploading") {
    const done = state.progress >= 1;
    return (
      <div className="upload-panel" aria-live="polite">
        <FileLine file={state.file} />
        <p className="upload-panel__status">
          {done
            ? t("upload.waiting")
            : t("upload.sending", { percent: Math.round(state.progress * 100), size: formatBytes(state.file.size) })}
        </p>
        <ProgressBar value={done ? null : state.progress} label={t("upload.progressLabel")} />
        {!done && (
          <div className="upload-panel__actions">
            <Button onClick={uploader.cancel}>{t("upload.cancel")}</Button>
          </div>
        )}
      </div>
    );
  }

  if (state.phase === "error") {
    return (
      <div className="upload-panel upload-panel--plain">
        <Notice tone="error" title={state.file ? t("upload.failedNamed", { name: state.file.name }) : t("upload.failed")}>
          <p>{state.message}</p>
          <p className="notice__action notice__buttons">
            <Button onClick={uploader.pick}>{t("upload.chooseAnother")}</Button>
            <Button variant="quiet" onClick={uploader.dismiss}>
              {t("common.dismiss")}
            </Button>
          </p>
        </Notice>
      </div>
    );
  }

  return null;
}

function fileKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

/** Each new file starts with OCR on: it only runs on pages without usable text. */
function ChosenFile({ file, uploader }: { file: File; uploader: Uploader }) {
  const [useOcr, setUseOcr] = useState(true);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Move focus here so keyboard and screen-reader users land on the next step.
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <section className="upload-panel" aria-labelledby="upload-panel-title">
      <h2 id="upload-panel-title" className="upload-panel__title" ref={headingRef} tabIndex={-1}>
        {t("upload.readyTitle")}
      </h2>
      <FileLine file={file} />

      <fieldset className="choice">
        <legend className="choice__legend">{t("upload.readingLegend")}</legend>
        <label className="choice__option">
          <input type="radio" name="reading" checked={useOcr} onChange={() => setUseOcr(true)} />
          <span>
            <span className="choice__label">{t("upload.ocrOn")}</span>
            <span className="choice__hint">{t("upload.ocrOnHint")}</span>
          </span>
        </label>
        <label className="choice__option">
          <input type="radio" name="reading" checked={!useOcr} onChange={() => setUseOcr(false)} />
          <span>
            <span className="choice__label">{t("upload.ocrOff")}</span>
            <span className="choice__hint">{t("upload.ocrOffHint")}</span>
          </span>
        </label>
      </fieldset>

      <div className="upload-panel__actions">
        <Button variant="quiet" onClick={uploader.pick}>
          {t("upload.chooseAnother")}
        </Button>
        <Button onClick={uploader.dismiss}>{t("common.cancel")}</Button>
        <Button variant="primary" onClick={() => void uploader.upload(useOcr)}>
          {t("upload.start")}
        </Button>
      </div>
    </section>
  );
}

function FileLine({ file }: { file: File }) {
  return (
    <p className="upload-panel__file">
      <svg className="upload-panel__icon" width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M5 2.75h6.5L15.25 6.5v10.75H5z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
        <path d="M11.25 2.75V6.75h4" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
      <span className="upload-panel__name" title={file.name} lang={langOf(file.name)}>
        {file.name}
      </span>
      <span className="upload-panel__size">{formatBytes(file.size)}</span>
    </p>
  );
}
