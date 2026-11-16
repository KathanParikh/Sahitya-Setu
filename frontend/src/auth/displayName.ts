/**
 * The name to show for the signed-in user.
 *
 * Sign-up in this app collects only an email and a password, so Supabase
 * holds no username unless one was added to the user's metadata some other
 * way (the Supabase dashboard, or an OAuth provider). The usual metadata keys
 * are checked first; otherwise the part of the email before "@" is used.
 * Nothing is invented.
 */
const NAME_KEYS = ["username", "display_name", "full_name", "name", "user_name"] as const;

interface UserLike {
  email?: string | null;
  user_metadata?: Record<string, unknown> | null;
}

export function displayName(user: UserLike | null | undefined): string {
  const meta = user?.user_metadata ?? {};
  for (const key of NAME_KEYS) {
    const value = meta[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  const email = user?.email?.trim() ?? "";
  return email.includes("@") ? email.slice(0, email.indexOf("@")) : email;
}

/** The avatar's letter: the first character of the shown name, upper-cased. */
export function initialOf(name: string): string {
  const first = Array.from(name.trim())[0];
  return first ? first.toLocaleUpperCase() : "?";
}
