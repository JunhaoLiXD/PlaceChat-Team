"use client";

import type { Session } from "@supabase/supabase-js";

import { getSupabaseBrowserClient } from "@/lib/supabase";

let pendingSession: Promise<Session> | undefined;

async function readOrCreateSession(): Promise<Session> {
  const { auth } = getSupabaseBrowserClient();
  const existing = await auth.getSession();
  if (existing.error) throw existing.error;
  if (existing.data.session) return existing.data.session;

  // No name, email, password, or personal metadata is requested or supplied.
  const created = await auth.signInAnonymously();
  if (created.error) throw created.error;
  if (!created.data.session) {
    throw new Error("Anonymous sign-in did not return a session.");
  }
  return created.data.session;
}

async function readWithTabLock(): Promise<Session> {
  // Serialize first visits in different tabs, then re-read shared storage inside
  // the lock. This lock is separate from Supabase's internal auth storage lock.
  if (typeof navigator !== "undefined" && navigator.locks) {
    return await navigator.locks.request(
      "placechat:anonymous-session",
      readOrCreateSession,
    );
  }
  return readOrCreateSession();
}

/** Reuse storage on every call, sharing only work that is currently in flight. */
export function ensureSession(): Promise<Session> {
  if (!pendingSession) {
    const task = readWithTabLock();
    pendingSession = task.finally(() => {
      pendingSession = undefined;
    });
  }
  return pendingSession;
}

/** Read auth again for each API request, so refreshed tokens are never cached here. */
export async function getAccessToken(): Promise<string> {
  return (await ensureSession()).access_token;
}
