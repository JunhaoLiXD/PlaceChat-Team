import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { Activity } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  ADMIN_REPORT_REFRESH_MS,
  AdminReportManager,
} from "@/components/admin-report-manager";
import { ADMIN_SIGNED_OUT_EVENT } from "@/lib/admin-auth";
import { ApiRequestError } from "@/lib/placechat-api";
import type { AdminReport, SenderBlock } from "@/lib/placechat-types";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  remove: vi.fn(),
  dismiss: vi.fn(),
  block: vi.fn(),
}));

vi.mock("@/lib/placechat-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/placechat-api")>()),
  listAdminReports: mocks.list,
  removeReportedMessage: mocks.remove,
  dismissAdminReport: mocks.dismiss,
  blockReportedSender: mocks.block,
}));

const firstReport: AdminReport = {
  id: "report-1",
  message_id: "message-1",
  room_id: "room-1",
  reason: "harassment",
  status: "pending",
  created_at: "2026-11-10T14:01:00Z",
  message: {
    id: "message-1",
    room_id: "room-1",
    body: "An unsafe message",
    nickname: "Quiet Otter",
    created_at: "2026-11-10T14:00:00Z",
  },
  room: { id: "room-1", name: "Library West", description: "Quiet floors." },
};

const secondReport: AdminReport = {
  ...firstReport,
  id: "report-2",
  message_id: "message-2",
  room_id: "room-2",
  reason: null,
  message: {
    ...firstReport.message,
    id: "message-2",
    room_id: "room-2",
    body: "Another reported message",
    nickname: "Calm Fox",
  },
  room: { id: "room-2", name: "Reitz Union", description: "Student union." },
};

const senderBlock: SenderBlock = {
  id: "block-1",
  created_at: "2026-11-27T14:00:00Z",
  expires_at: "2026-11-27T15:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.list.mockResolvedValue([firstReport, secondReport]);
  mocks.remove.mockResolvedValue(undefined);
  mocks.dismiss.mockResolvedValue(undefined);
  mocks.block.mockResolvedValue(senderBlock);
});

afterEach(cleanup);

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

async function renderReports() {
  const view = render(<AdminReportManager />);
  await screen.findByText("An unsafe message");
  return view;
}

function confirmBlock(nickname = "Quiet Otter") {
  fireEvent.click(
    screen.getByRole("button", { name: `Block sender ${nickname}` }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Confirm block" }));
}

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

test("clears loaded reports and hides the queue while access is rechecked after sign-out", async () => {
  render(<AdminReportManager />);
  expect(await screen.findByText("An unsafe message")).toBeDefined();
  mocks.list.mockRejectedValueOnce(
    new ApiRequestError("Not authorized", 401, "UNAUTHORIZED"),
  );

  act(() => window.dispatchEvent(new Event(ADMIN_SIGNED_OUT_EVENT)));

  expect(screen.queryByText("An unsafe message")).toBeNull();
  expect(screen.getByLabelText("Loading reports")).toBeDefined();
  expect(
    await screen.findByRole("heading", { name: "Not authorized" }),
  ).toBeDefined();
  expect(screen.queryByText("An unsafe message")).toBeNull();
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

test("reloads the queue when another admin already handled a report", async () => {
  mocks.remove.mockRejectedValue(
    new ApiRequestError("The report was not found.", 404, "NOT_FOUND"),
  );
  render(<AdminReportManager />);
  await screen.findByText("An unsafe message");
  mocks.list.mockResolvedValueOnce([secondReport]);

  fireEvent.click(
    screen.getByRole("button", { name: "Remove message from Quiet Otter" }),
  );

  await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(2));
  expect(screen.queryByText("An unsafe message")).toBeNull();
  expect(screen.getByText("Another reported message")).toBeDefined();
  expect(screen.getByText("1 pending")).toBeDefined();
  expect(screen.queryByRole("alert")).toBeNull();
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

test.each([15, 60, 1440] as const)(
  "blocks the reported sender for %i minutes and keeps the report available",
  async (minutes) => {
    render(<AdminReportManager />);
    await screen.findByText("An unsafe message");
    fireEvent.click(
      screen.getByRole("button", { name: "Block sender Quiet Otter" }),
    );

    const duration = screen.getByRole("combobox", { name: "Block duration" });
    expect(
      screen.getAllByRole("option").map((option) => option.textContent),
    ).toEqual(["15 minutes", "1 hour", "24 hours"]);
    fireEvent.change(duration, { target: { value: String(minutes) } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm block" }));

    await waitFor(() =>
      expect(mocks.block).toHaveBeenCalledWith("report-1", minutes),
    );
    expect((await screen.findByRole("status")).textContent).toBe(
      "Quiet Otter is blocked from sending in all rooms until Nov 27, 2026, 10:00 AM Eastern Time.",
    );
    expect(screen.getByText("An unsafe message")).toBeDefined();
    expect(screen.getByText("2 pending")).toBeDefined();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(mocks.remove).not.toHaveBeenCalled();
    expect(mocks.dismiss).not.toHaveBeenCalled();
  },
);

test("cancels blocking without sending a request", async () => {
  render(<AdminReportManager />);
  await screen.findByText("An unsafe message");
  fireEvent.click(
    screen.getByRole("button", { name: "Block sender Quiet Otter" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("combobox")).toBeNull();
  expect(mocks.block).not.toHaveBeenCalled();
});

test("shows block failures and permits retrying with the selected duration", async () => {
  mocks.block.mockRejectedValueOnce(
    new ApiRequestError("The server is unavailable.", 0),
  );
  render(<AdminReportManager />);
  await screen.findByText("An unsafe message");
  fireEvent.click(
    screen.getByRole("button", { name: "Block sender Quiet Otter" }),
  );
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "1440" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm block" }));

  expect((await screen.findByRole("alert")).textContent).toBe(
    "The server is unavailable.",
  );
  expect(screen.getByRole("combobox")).toHaveProperty("value", "1440");
  fireEvent.click(screen.getByRole("button", { name: "Confirm block" }));
  await screen.findByRole("status");
  expect(mocks.block).toHaveBeenNthCalledWith(2, "report-1", 1440);
  expect(screen.queryByRole("alert")).toBeNull();
});

test("locks moderation controls while a block is pending", async () => {
  const pending = deferred<SenderBlock>();
  mocks.block.mockReturnValueOnce(pending.promise);
  await renderReports();
  confirmBlock("Calm Fox");
  expect(screen.getByRole("button", { name: "Blocking…" })).toHaveProperty(
    "disabled",
    true,
  );
  expect(screen.getByRole("combobox")).toHaveProperty("disabled", true);
  expect(
    screen.getByRole("button", { name: "Remove message from Quiet Otter" }),
  ).toHaveProperty("disabled", true);
  expect(mocks.block).toHaveBeenCalledTimes(1);
  await act(async () => pending.resolve(senderBlock));
  expect(screen.getByRole("status").textContent).toMatch(
    /^Calm Fox is blocked/,
  );
});

test.each([401, 403])(
  "shows revoked access after a block returns %i",
  async (status) => {
    mocks.block.mockRejectedValueOnce(
      new ApiRequestError("Access denied", status),
    );
    render(<AdminReportManager />);
    await screen.findByText("An unsafe message");
    fireEvent.click(
      screen.getByRole("button", { name: "Block sender Quiet Otter" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm block" }));
    expect(
      await screen.findByRole("heading", { name: "Not authorized" }),
    ).toBeDefined();
    expect(screen.queryByText("An unsafe message")).toBeNull();
  },
);

test("refreshes a missing report and explains the failed block", async () => {
  mocks.block.mockRejectedValueOnce(new ApiRequestError("Missing report", 404));
  render(<AdminReportManager />);
  await screen.findByText("An unsafe message");
  mocks.list.mockResolvedValueOnce([secondReport]);
  fireEvent.click(
    screen.getByRole("button", { name: "Block sender Quiet Otter" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Confirm block" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(
    /no longer available/,
  );
  await waitFor(() =>
    expect(screen.queryByText("An unsafe message")).toBeNull(),
  );
  expect(screen.getByText("1 pending")).toBeDefined();
});

test("ignores a late block result after administrator sign-out", async () => {
  const pending = deferred<SenderBlock>();
  mocks.block.mockReturnValueOnce(pending.promise);
  await renderReports();
  confirmBlock();
  mocks.list.mockRejectedValueOnce(new ApiRequestError("Signed out", 401));
  act(() => window.dispatchEvent(new Event(ADMIN_SIGNED_OUT_EVENT)));
  await screen.findByRole("heading", { name: "Not authorized" });
  await act(async () => pending.resolve(senderBlock));
  expect(screen.queryByRole("status")).toBeNull();
});

test.each([
  ["block", "success"],
  ["remove", "success"],
  ["dismiss", "success"],
  ["block", "error"],
  ["remove", "error"],
  ["dismiss", "error"],
] as const)(
  "reopening Reports after a pending %s resets controls and ignores its late %s",
  async (action, outcome) => {
    const oldRequest = deferred<SenderBlock | undefined>();
    mocks[action].mockReturnValueOnce(oldRequest.promise);
    const page = (mode: "visible" | "hidden") => (
      <Activity mode={mode}>
        <AdminReportManager />
      </Activity>
    );
    const view = render(page("visible"));
    await screen.findByText("An unsafe message");
    if (action === "block") {
      confirmBlock();
    } else {
      fireEvent.click(
        screen.getByRole("button", {
          name:
            action === "remove"
              ? "Remove message from Quiet Otter"
              : "Dismiss report for Quiet Otter",
        }),
      );
    }
    expect(mocks[action]).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("button", { name: "Block sender Quiet Otter" }),
    ).toHaveProperty("disabled", true);

    view.rerender(page("hidden"));
    view.rerender(page("visible"));
    await waitFor(() => {
      expect(mocks.list).toHaveBeenCalledTimes(2);
      for (const button of screen.getAllByRole("button"))
        expect(button).toHaveProperty("disabled", false);
    });

    // An old completion must not clear a different action in the reopened visit.
    const currentRequest = deferred<void>();
    mocks.dismiss.mockReturnValueOnce(currentRequest.promise);
    fireEvent.click(
      screen.getByRole("button", { name: "Dismiss report for Calm Fox" }),
    );
    await act(async () => {
      if (outcome === "error")
        oldRequest.reject(new ApiRequestError("Old access denied", 403));
      else oldRequest.resolve(senderBlock);
    });
    expect(screen.getByText("An unsafe message")).toBeDefined();
    expect(screen.getByText("Another reported message")).toBeDefined();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Dismiss report for Calm Fox" }),
    ).toHaveProperty("disabled", true);

    await act(async () => currentRequest.resolve());
    expect(screen.queryByText("Another reported message")).toBeNull();
    expect(screen.getByText("1 pending")).toBeDefined();
    expect(
      screen.getByRole("button", { name: "Block sender Quiet Otter" }),
    ).toHaveProperty("disabled", false);
  },
);
