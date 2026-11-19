"use client";

import type { Session } from "@supabase/supabase-js";

import { getSupabaseBrowserClient } from "@/lib/supabase";

export async function signInWithPassword(
  email: string,
  password: string,
): Promise<Session> {
  const { data, error } =
    await getSupabaseBrowserClient().auth.signInWithPassword({
      email,
      password,
    });

  if (error) throw error;
  if (!data.session) throw new Error("Sign-in did not return a session.");
  return data.session;
}

export async function signOutAdmin(): Promise<void> {
  const { error } = await getSupabaseBrowserClient().auth.signOut();
  if (error) throw error;
}
