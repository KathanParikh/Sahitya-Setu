import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { AuthError, Session } from "@supabase/supabase-js";
import { useQueryClient } from "@tanstack/react-query";
import type { AuthFailure } from "./authErrors";
import { supabase } from "./supabase";

export interface SignUpResult {
  error: AuthFailure | null;
  /**
   * True when Supabase created the account but returned no session: email
   * confirmation is on, and the user must open the link before signing in.
   * When confirmation is off, a session is returned and the user is signed in.
   */
  needsConfirmation: boolean;
}

interface AuthState {
  session: Session | null;
  /** True until the stored session has been read on start-up. */
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: AuthFailure | null }>;
  signUp: (email: string, password: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

const NOT_CONFIGURED: AuthFailure = { message: "Supabase is not configured.", status: 500 };

function failure(error: AuthError): AuthFailure {
  return { code: error.code, message: error.message, status: error.status };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((event, next) => {
      setSession(next);
      // Another user's books must never stay in the cache after sign-out.
      if (event === "SIGNED_OUT") queryClient.clear();
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, [queryClient]);

  const value = useMemo<AuthState>(
    () => ({
      session,
      loading,
      async signIn(email, password) {
        if (!supabase) return { error: NOT_CONFIGURED };
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        return { error: error ? failure(error) : null };
      },
      async signUp(email, password) {
        if (!supabase) return { error: NOT_CONFIGURED, needsConfirmation: false };
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          // Where the confirmation link returns to. It must be listed under
          // Supabase -> Auth -> URL Configuration -> Redirect URLs.
          options: { emailRedirectTo: `${window.location.origin}/` },
        });
        if (error) return { error: failure(error), needsConfirmation: false };
        // With confirmation on, an already-registered email returns a user with
        // no session (and no identities), so the screen never reveals whether
        // an address has an account. Both cases show "check your email".
        return { error: null, needsConfirmation: !data.session };
      },
      async signOut() {
        await supabase?.auth.signOut();
      },
    }),
    [session, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
