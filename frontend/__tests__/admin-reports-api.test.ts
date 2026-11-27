import { afterEach, beforeEach, expect, test, vi } from "vitest";

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example.test";
  process.env.NEXT_PUBLIC_USE_MOCKS = "false";
});

const session = vi.hoisted(() => ({
  getAccessToken: vi.fn().mockResolvedValue("admin-access-token"),
}));

vi.mock("@/lib/session", () => session);

const {
  blockReportedSender,
  dismissAdminReport,
  listAdminReports,
  removeReportedMessage,
} = await import("@/lib/placechat-api");

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

test.each([15, 60, 1440] as const)(
  "blocks by report ID with a %i-minute duration",
  async (minutes) => {
    const block = {
      id: "block-1",
      created_at: "2026-11-27T12:00:00Z",
      expires_at: "2026-11-28T12:00:00Z",
    };
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(block), { status: 200 }),
    );
    await expect(blockReportedSender("report-1", minutes)).resolves.toEqual(
      block,
    );
    expectAuthorizedPost("/api/v1/admin/blocks", 0);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      report_id: "report-1",
      duration_minutes: minutes,
    });
  },
);
