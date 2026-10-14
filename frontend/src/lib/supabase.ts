"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { publicConfig } from "@/lib/config";

let browserClient: SupabaseClient | undefined;

/** One browser client shares persisted auth and refreshes it automatically. */
export function getSupabaseBrowserClient(): SupabaseClient {
  if (typeof window === "undefined") {
    throw new Error("Supabase browser sessions require a browser.");
  }

  if (!browserClient) {
    if (
      !publicConfig.supabaseUrl ||
      !publicConfig.supabasePublishableKey.startsWith("sb_publishable_")
    ) {
      throw new Error("Supabase URL and publishable key are not configured.");
    }

    browserClient = createClient(
      publicConfig.supabaseUrl,
      publicConfig.supabasePublishableKey,
      {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: false,
        },
      },
    );
  }

  return browserClient;
}
