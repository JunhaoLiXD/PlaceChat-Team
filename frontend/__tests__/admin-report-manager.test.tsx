import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  ADMIN_REPORT_REFRESH_MS,
  AdminReportManager,
} from "@/components/admin-report-manager";
import { ApiRequestError } from "@/lib/placechat-api";
import type { AdminReport } from "@/lib/placechat-types";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  remove: vi.fn(),
  dismiss: vi.fn(),
}));

vi.mock("@/lib/placechat-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/placechat-api")>()),
  listAdminReports: mocks.list,
  removeReportedMessage: mocks.remove,
  dismissAdminReport: mocks.dismiss,
}));

const firstReport: AdminReport = {
  id: "report-1",
  reason: "harassment",
  created_at: "2026-11-10T14:01:00Z",
  message: {
    id: "message-1",
    body: "An unsafe message",
    nickname: "Quiet Otter",
    created_at: "2026-11-10T14:00:00Z",
  },
  room: { id: "room-1", name: "Library West" },
};

const secondReport: AdminReport = {
  ...firstReport,
  id: "report-2",
  reason: null,
  message: {
    ...firstReport.message,
    id: "message-2",
    body: "Another reported message",
    nickname: "Calm Fox",
  },
  room: { id: "room-2", name: "Reitz Union" },
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.list.mockResolvedValue([firstReport, secondReport]);
  mocks.remove.mockResolvedValue(undefined);
  mocks.dismiss.mockResolvedValue(undefined);
});

afterEach(cleanup);

test("lists pending reports and schedules a 30-second refresh", async () => {
  const intervalSpy = vi.spyOn(window, "setInterval");
  render(<AdminReportManager />);

  expect(await screen.findByText("An unsafe message")).toBeDefined();
  expect(screen.getByText("Another reported message")).toBeDefined();
  expect(screen.getByText(/Library West/)).toBeDefined();
  expect(screen.getAllByText("Nov 10, 2026, 9:00 AM")).toHaveLength(2);
  expect(screen.getByText("Harassment")).toBeDefined();
  expect(screen.getByText("No reason")).toBeDefined();
  expect(screen.getByText("2 pending")).toBeDefined();
  expect(intervalSpy).toHaveBeenCalledWith(
    expect.any(Function),
    ADMIN_REPORT_REFRESH_MS,
  );
  const refresh = intervalSpy.mock.calls.find(
    ([, delay]) => delay === ADMIN_REPORT_REFRESH_MS,
  )?.[0] as TimerHandler;
  mocks.list.mockResolvedValueOnce([firstReport]);
  act(() => {
    if (typeof refresh === "function") refresh();
  });
  await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(2));
  expect(screen.getByText("1 pending")).toBeDefined();
  intervalSpy.mockRestore();
});

test("removes a reported message from the pending queue", async () => {
  render(<AdminReportManager />);
  await screen.findByText("An unsafe message");

  fireEvent.click(
    screen.getByRole("button", { name: "Remove message from Quiet Otter" }),
  );

  await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith("report-1"));
  expect(screen.queryByText("An unsafe message")).toBeNull();
  expect(screen.getByText("1 pending")).toBeDefined();
});

test("dismisses a report without removing other rows", async () => {
  render(<AdminReportManager />);
  await screen.findByText("Another reported message");

  fireEvent.click(
    screen.getByRole("button", { name: "Dismiss report for Calm Fox" }),
  );

  await waitFor(() => expect(mocks.dismiss).toHaveBeenCalledWith("report-2"));
  expect(screen.queryByText("Another reported message")).toBeNull();
  expect(screen.getByText("An unsafe message")).toBeDefined();
});

test("shows API action failures without dropping the report", async () => {
  mocks.remove.mockRejectedValue(
    new ApiRequestError("The report was already handled.", 409, "CONFLICT"),
  );
  render(<AdminReportManager />);
  await screen.findByText("An unsafe message");

  fireEvent.click(
    screen.getByRole("button", { name: "Remove message from Quiet Otter" }),
  );

  expect((await screen.findByRole("alert")).textContent).toBe(
    "The report was already handled.",
  );
  expect(screen.getByText("An unsafe message")).toBeDefined();
});

test("shows the protected-page message to a non-admin", async () => {
  mocks.list.mockRejectedValue(
    new ApiRequestError("You are not allowed to do this.", 403, "FORBIDDEN"),
  );
  render(<AdminReportManager />);

  expect(
    await screen.findByRole("heading", { name: "Not authorized" }),
  ).toBeDefined();
  expect(screen.getByRole("alert").textContent).toMatch(/only available/i);
  expect(
    screen.getByRole("link", { name: /return to admin sign in/i }),
  ).toHaveProperty("href", expect.stringContaining("/admin/login"));
});
