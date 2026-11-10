import { afterEach, beforeEach, expect, test, vi } from "vitest";

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example.test";
  process.env.NEXT_PUBLIC_USE_MOCKS = "false";
});

const session = vi.hoisted(() => ({
  getAccessToken: vi.fn().mockResolvedValue("admin-access-token"),
}));

vi.mock("@/lib/session", () => session);

const { dismissAdminReport, listAdminReports, removeReportedMessage } =
  await import("@/lib/placechat-api");

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.resetAllMocks();
  session.getAccessToken.mockResolvedValue("admin-access-token");
  fetchMock.mockImplementation(
    async () =>
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

function expectAuthorizedPost(path: string, callIndex: number) {
  const [input, init] = fetchMock.mock.calls[callIndex];
  expect(String(input)).toBe(`https://api.example.test${path}`);
  expect(init?.method).toBe("POST");
  expect(new Headers(init?.headers).get("Authorization")).toBe(
    "Bearer admin-access-token",
  );
}

test("loads only pending reports with administrator authentication", async () => {
  await expect(listAdminReports()).resolves.toEqual([]);

  const [input, init] = fetchMock.mock.calls[0];
  expect(String(input)).toBe(
    "https://api.example.test/api/v1/admin/reports?status=pending",
  );
  expect(new Headers(init?.headers).get("Authorization")).toBe(
    "Bearer admin-access-token",
  );
  expect(init?.cache).toBe("no-store");
});

test("uses the remove-message and dismiss actions", async () => {
  await removeReportedMessage("report-1");
  await dismissAdminReport("report-2");

  expectAuthorizedPost("/api/v1/admin/reports/report-1/remove-message", 0);
  expectAuthorizedPost("/api/v1/admin/reports/report-2/dismiss", 1);
});
