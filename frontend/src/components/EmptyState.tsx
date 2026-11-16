import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  /** Heading level; 1 when the state is the whole page. */
  level?: 1 | 2;
  children?: ReactNode;
  /** Buttons or links below the text. */
  action?: ReactNode;
}

/** A short title, an explanation and an optional next step. */
export function EmptyState({ title, level = 2, children, action }: EmptyStateProps) {
  const Heading = level === 1 ? "h1" : "h2";
  return (
    <div className="empty-state">
      <Heading className="empty-state__title">{title}</Heading>
      {children && <div className="empty-state__body">{children}</div>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}
