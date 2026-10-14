import type { Session } from "@supabase/supabase-js";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  signInAnonymously: vi.fn(),
}));

vi.mock("@/lib/supabase", () => ({
  getSupabaseBrowserClient: () => ({ auth }),
}));

function session(accessToken = "test-access-token"): Session {
  return {
    access_token: accessToken,
    refresh_token: "test-refresh-token",
    token_type: "bearer",
    expires_in: 3600,
    user: {
      id: "test-user-id",
      aud: "authenticated",
      app_metadata: {},
      user_metadata: {},
      created_at: "2026-10-14T00:00:00Z",
      is_anonymous: true,
    },
  };
}

beforeEach(() => {
  vi.resetModules();
  vi.resetAllMocks();
  vi.stubGlobal("navigator", {});
  auth.getSession.mockResolvedValue({ data: { session: null }, error: null });
  auth.signInAnonymously.mockResolvedValue({
    data: { session: session() },
    error: null,
  });
});

afterEach(() => vi.unstubAllGlobals());

describe("ensureSession", () => {
  test("signs in anonymously without personal data only when no session exists", async () => {
    const { ensureSession } = await import("@/lib/session");
    const result = await ensureSession();
    expect(result.user.is_anonymous).toBe(true);
    expect(auth.getSession).toHaveBeenCalledOnce();
    expect(auth.signInAnonymously).toHaveBeenCalledExactlyOnceWith();
  });

  test("reuses the persisted session across calls and a module reload", async () => {
    const persisted = session();
    auth.getSession.mockResolvedValue({
      data: { session: persisted },
      error: null,
    });
    const firstPage = await import("@/lib/session");
    expect(await firstPage.ensureSession()).toBe(persisted);
    expect(await firstPage.ensureSession()).toBe(persisted);
    vi.resetModules();
    const refreshedPage = await import("@/lib/session");
    expect(await refreshedPage.ensureSession()).toBe(persisted);
    expect(auth.signInAnonymously).not.toHaveBeenCalled();
    expect(auth.getSession).toHaveBeenCalledTimes(3);
  });

  test("preserves an existing non-anonymous session", async () => {
    const persisted = session();
    persisted.user.is_anonymous = false;
    auth.getSession.mockResolvedValue({
      data: { session: persisted },
      error: null,
    });
    const { ensureSession } = await import("@/lib/session");
    expect(await ensureSession()).toBe(persisted);
    expect(auth.signInAnonymously).not.toHaveBeenCalled();
  });

  test("deduplicates concurrent calls", async () => {
    const { ensureSession } = await import("@/lib/session");
    const first = ensureSession();
    expect(ensureSession()).toBe(first);
    const results = await Promise.all([
      first,
      ensureSession(),
      ensureSession(),
    ]);
    expect(results.every((result) => result === results[0])).toBe(true);
    expect(auth.getSession).toHaveBeenCalledOnce();
    expect(auth.signInAnonymously).toHaveBeenCalledOnce();
  });

  test("serializes simultaneous first visits across tabs and re-reads persisted auth", async () => {
    let persisted: Session | null = null;
    let tail = Promise.resolve();
    const request = vi.fn((_name: string, callback: () => Promise<Session>) => {
      const result = tail.then(callback);
      tail = result.then(() => undefined);
      return result;
    });
    vi.stubGlobal("navigator", { locks: { request } });
    auth.getSession.mockImplementation(async () => ({
      data: { session: persisted },
      error: null,
    }));
    auth.signInAnonymously.mockImplementation(async () => {
      persisted = session();
      return { data: { session: persisted }, error: null };
    });
    const firstTab = await import("@/lib/session");
    vi.resetModules();
    const secondTab = await import("@/lib/session");
    const [first, second] = await Promise.all([
      firstTab.ensureSession(),
      secondTab.ensureSession(),
    ]);
    expect(first).toBe(second);
    expect(request).toHaveBeenCalledTimes(2);
    expect(auth.getSession).toHaveBeenCalledTimes(2);
    expect(auth.signInAnonymously).toHaveBeenCalledOnce();
  });

  test("propagates storage/refresh errors without creating a replacement identity", async () => {
    const error = new Error("Session refresh failed");
    auth.getSession.mockResolvedValueOnce({ data: { session: null }, error });
    const { ensureSession } = await import("@/lib/session");
    await expect(ensureSession()).rejects.toBe(error);
    expect(auth.signInAnonymously).not.toHaveBeenCalled();
    auth.getSession.mockResolvedValue({
      data: { session: session() },
      error: null,
    });
    await expect(ensureSession()).resolves.toBeDefined();
  });

  test("propagates sign-in errors and permits a retry", async () => {
    const error = new Error("Sign-in unavailable");
    auth.signInAnonymously.mockResolvedValueOnce({
      data: { session: null },
      error,
    });
    const { ensureSession } = await import("@/lib/session");
    await expect(ensureSession()).rejects.toBe(error);
    await expect(ensureSession()).resolves.toBeDefined();
    expect(auth.signInAnonymously).toHaveBeenCalledTimes(2);
  });

  test("does not swallow thrown SDK errors", async () => {
    const error = new Error("Storage unavailable");
    auth.getSession.mockRejectedValueOnce(error);
    const { ensureSession } = await import("@/lib/session");
    await expect(ensureSession()).rejects.toBe(error);
    expect(auth.signInAnonymously).not.toHaveBeenCalled();
  });

  test("rejects sign-in without a returned session", async () => {
    auth.signInAnonymously.mockResolvedValueOnce({
      data: { session: null },
      error: null,
    });
    const { ensureSession } = await import("@/lib/session");
    await expect(ensureSession()).rejects.toThrow("did not return a session");
  });
});

test("getAccessToken reads the refreshed session for each API request", async () => {
  auth.getSession
    .mockResolvedValueOnce({
      data: { session: session("first-token") },
      error: null,
    })
    .mockResolvedValueOnce({
      data: { session: session("refreshed-token") },
      error: null,
    });
  const { getAccessToken } = await import("@/lib/session");
  expect(await getAccessToken()).toBe("first-token");
  expect(await getAccessToken()).toBe("refreshed-token");
  expect(auth.getSession).toHaveBeenCalledTimes(2);
});
