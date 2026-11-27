import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/lib/session", () => ({
  getAccessToken: vi.fn().mockResolvedValue("test-token"),
}));

vi.mock("@/lib/config", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/config")>()),
  publicConfig: { apiBaseUrl: "http://api.test" },
  shouldUseMocks: () => false,
}));

import {
  ApiRequestError,
  deleteBlockedWord,
  sendRoomMessage,
} from "@/lib/placechat-api";

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

test.each(["2026-11-27T12:15:00Z", undefined, 42])(
  "carries a string error.until through ApiRequestError (%s)",
  async (until) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "BLOCKED",
              message: "Temporarily blocked.",
              until,
            },
          }),
          { status: 403 },
        ),
      ),
    );

    const error = await sendRoomMessage("room-1", "draft", "Quiet Otter").catch(
      (caught: unknown) => caught,
    );
    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({
      status: 403,
      code: "BLOCKED",
      message: "Temporarily blocked.",
      until: typeof until === "string" ? until : undefined,
    });
  },
);
