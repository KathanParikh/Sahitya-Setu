/** Build-time settings from .env.local (see .env.example). */

export interface AppConfig {
  apiUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
}

const env = import.meta.env;

export const config: AppConfig = {
  apiUrl: (env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, ""),
  supabaseUrl: (env.VITE_SUPABASE_URL || "").replace(/\/+$/, ""),
  supabaseAnonKey: env.VITE_SUPABASE_ANON_KEY || "",
};

/** Names of required settings that are not set; empty when the app can start. */
export const missingSettings: string[] = [
  !config.supabaseUrl && "VITE_SUPABASE_URL",
  !config.supabaseAnonKey && "VITE_SUPABASE_ANON_KEY",
].filter((name): name is string => Boolean(name));
