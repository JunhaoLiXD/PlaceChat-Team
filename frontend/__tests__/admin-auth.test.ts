import { beforeEach, expect, test, vi } from "vitest";

const auth = vi.hoisted(() => ({
  signInWithPassword: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("@/lib/supabase", () => ({
  getSupabaseBrowserClient: () => ({ auth }),
}));

beforeEach(() => vi.resetAllMocks());

test("signs in through Supabase email/password auth", async () => {
  const session = { access_token: "admin-token" };
  auth.signInWithPassword.mockResolvedValue({
    data: { session },
    error: null,
  });
  const { signInWithPassword } = await import("@/lib/admin-auth");

  await expect(signInWithPassword("admin@example.edu", "secret")).resolves.toBe(
    session,
  );
  expect(auth.signInWithPassword).toHaveBeenCalledExactlyOnceWith({
    email: "admin@example.edu",
    password: "secret",
  });
});

test("notifies mounted admin views after a successful sign-out", async () => {
  auth.signOut.mockResolvedValue({ error: null });
  const listener = vi.fn();
  const { ADMIN_SIGNED_OUT_EVENT, signOutAdmin } =
    await import("@/lib/admin-auth");
  window.addEventListener(ADMIN_SIGNED_OUT_EVENT, listener);

  await signOutAdmin();

  expect(listener).toHaveBeenCalledOnce();
  window.removeEventListener(ADMIN_SIGNED_OUT_EVENT, listener);
});

test("propagates Supabase sign-in and sign-out failures", async () => {
  const signInError = new Error("sign-in failed");
  const signOutError = new Error("sign-out failed");
  auth.signInWithPassword.mockResolvedValue({
    data: { session: null },
    error: signInError,
  });
  auth.signOut.mockResolvedValue({ error: signOutError });
  const { signInWithPassword, signOutAdmin } = await import("@/lib/admin-auth");

  await expect(signInWithPassword("admin@example.edu", "bad")).rejects.toBe(
    signInError,
  );
  await expect(signOutAdmin()).rejects.toBe(signOutError);
});
