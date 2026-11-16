import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { config, missingSettings } from "../config";

/**
 * Browser Supabase client, used for sign-in only. Created with the anon key;
 * the backend checks each access token with Supabase itself.
 * Null when the settings are missing (the app then shows a setup screen).
 */
export const supabase: SupabaseClient | null = missingSettings.length
  ? null
  : createClient(config.supabaseUrl, config.supabaseAnonKey, {
      auth: { persistSession: true, autoRefreshToken: true },
    });

/** The current access token, refreshed by Supabase if it is about to expire. */
export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
