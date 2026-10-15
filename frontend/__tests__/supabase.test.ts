import { afterEach, beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createClient: vi.fn(),
  publicConfig: {
    supabaseUrl: "https://test-project.supabase.co",
    supabasePublishableKey: "sb_publishable_test-placeholder",
  },
}));

vi.mock("@supabase/supabase-js", () => ({ createClient: mocks.createClient }));
vi.mock("@/lib/config", () => ({ publicConfig: mocks.publicConfig }));

beforeEach(() => {
  vi.resetModules();
  vi.resetAllMocks();
  mocks.publicConfig.supabaseUrl = "https://test-project.supabase.co";
  mocks.publicConfig.supabasePublishableKey = "sb_publishable_test-placeholder";
});

afterEach(() => vi.unstubAllGlobals());

test("shares one client with persistence and automatic refresh using only the publishable key", async () => {
  const client = { auth: {} };
  mocks.createClient.mockReturnValue(client);
  const { getSupabaseBrowserClient } = await import("@/lib/supabase");
  expect(getSupabaseBrowserClient()).toBe(client);
  expect(getSupabaseBrowserClient()).toBe(client);
  expect(mocks.createClient).toHaveBeenCalledExactlyOnceWith(
    mocks.publicConfig.supabaseUrl,
    mocks.publicConfig.supabasePublishableKey,
    {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      },
    },
  );
});

test.each(["url", "key"])(
  "rejects missing %s configuration before creating a client",
  async (field) => {
    if (field === "url") mocks.publicConfig.supabaseUrl = "";
    else mocks.publicConfig.supabasePublishableKey = "";
    const { getSupabaseBrowserClient } = await import("@/lib/supabase");
    expect(() => getSupabaseBrowserClient()).toThrow("not configured");
    expect(mocks.createClient).not.toHaveBeenCalled();
  },
);

test("rejects a key that is not publishable", async () => {
  mocks.publicConfig.supabasePublishableKey = "server-key-test-placeholder";
  const { getSupabaseBrowserClient } = await import("@/lib/supabase");
  expect(() => getSupabaseBrowserClient()).toThrow("not configured");
  expect(mocks.createClient).not.toHaveBeenCalled();
});

test("does not create a shared server session", async () => {
  vi.stubGlobal("window", undefined);
  const { getSupabaseBrowserClient } = await import("@/lib/supabase");
  expect(() => getSupabaseBrowserClient()).toThrow("require a browser");
  expect(mocks.createClient).not.toHaveBeenCalled();
});
