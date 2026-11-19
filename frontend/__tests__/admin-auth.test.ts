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
