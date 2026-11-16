import { en, type MessageKey, type Messages } from "./en";

export type Locale = "en";

const catalogs: Record<Locale, Messages> = { en };

// Interface language only. Book content, questions and answers carry their
// own language (marked with lang="gu" / lang="en" where they are rendered).
let locale: Locale = "en";

export function setLocale(next: Locale): void {
  locale = next;
  document.documentElement.lang = next;
}

export function getLocale(): Locale {
  return locale;
}

/** Interface text for `key`, with {name} placeholders filled from `vars`. */
export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  const template = catalogs[locale][key] ?? en[key];
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

export type { MessageKey };
