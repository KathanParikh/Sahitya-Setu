import type { ReactNode } from "react";

type Tone = "error" | "success" | "info";

interface NoticeProps {
  tone?: Tone;
  title: string;
  children?: ReactNode;
}

function Icon({ tone }: { tone: Tone }) {
  if (tone === "success") {
    return (
      <svg className="notice__icon" width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="10" r="8.25" stroke="currentColor" strokeWidth="1.5" />
        <path d="M6.5 10.2l2.3 2.3 4.7-4.9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg className="notice__icon" width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10 5.5v5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="10" cy="14" r="1" fill="currentColor" />
    </svg>
  );
}

/** A message with a coloured left rule: a title and an optional explanation. */
export function Notice({ tone = "info", title, children }: NoticeProps) {
  return (
    <div className={`notice notice--${tone}`} role={tone === "error" ? "alert" : "status"}>
      <Icon tone={tone} />
      <div>
        <p className="notice__title">{title}</p>
        {children && <div className="notice__body">{children}</div>}
      </div>
    </div>
  );
}
