import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/lib/session", () => ({
  getAccessToken: vi.fn().mockResolvedValue("test-token"),
}));

vi.mock("@/lib/config", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/config")>()),
  publicConfig: { apiBaseUrl: "http://api.test" },
}));

import { deleteBlockedWord } from "@/lib/placechat-api";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("a 204 No Content response resolves without parsing a body", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);

  await expect(deleteBlockedWord("word-1")).resolves.toBeUndefined();
  expect(fetchMock).toHaveBeenCalledWith(
    "http://api.test/api/v1/admin/blocked-words/word-1",
    expect.objectContaining({
      method: "DELETE",
      headers: expect.objectContaining({ Authorization: "Bearer test-token" }),
    }),
  );
});
