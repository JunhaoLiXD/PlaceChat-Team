import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AdminRoomManager } from "@/components/admin-room-manager";
import { ApiRequestError } from "@/lib/placechat-api";
import type { AdminRoom } from "@/lib/placechat-types";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  archive: vi.fn(),
}));

vi.mock("@/lib/placechat-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/placechat-api")>()),
  listAdminRooms: mocks.list,
  createAdminRoom: mocks.create,
  updateAdminRoom: mocks.update,
  archiveAdminRoom: mocks.archive,
}));

const activeRoom: AdminRoom = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Library West",
  description: "Quiet floors and group tables.",
  category: "library",
  latitude: 29.6513,
  longitude: -82.3429,
  status: "active",
  created_at: "2026-10-01T12:00:00Z",
  updated_at: "2026-10-01T12:00:00Z",
};

const archivedRoom: AdminRoom = {
  ...activeRoom,
  id: "22222222-2222-4222-8222-222222222222",
  name: "Old Study Hall",
  status: "archived",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.list.mockResolvedValue([activeRoom, archivedRoom]);
});

afterEach(cleanup);

test("lists active and archived rooms and creates a new room", async () => {
  const created: AdminRoom = {
    ...activeRoom,
    id: "33333333-3333-4333-8333-333333333333",
    name: "Newell Hall",
    description: "Open study space.",
    category: "academic",
    latitude: 29.6491,
    longitude: -82.3452,
  };
  mocks.create.mockResolvedValue(created);
  render(<AdminRoomManager />);

  expect(
    await screen.findByRole("heading", { name: "Library West" }),
  ).toBeDefined();
  expect(screen.getByRole("heading", { name: "Old Study Hall" })).toBeDefined();

  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "Newell Hall" },
  });
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "Open study space." },
  });
  fireEvent.change(screen.getByLabelText("Latitude"), {
    target: { value: "29.6491" },
  });
  fireEvent.change(screen.getByLabelText("Longitude"), {
    target: { value: "-82.3452" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create room" }));

  await waitFor(() =>
    expect(mocks.create).toHaveBeenCalledWith({
      name: "Newell Hall",
      description: "Open study space.",
      category: "academic",
      latitude: 29.6491,
      longitude: -82.3452,
    }),
  );
  expect(await screen.findByText("Created Newell Hall.")).toBeDefined();
  expect(screen.getByRole("heading", { name: "Newell Hall" })).toBeDefined();
});

test("edits an active room", async () => {
  const updated = { ...activeRoom, description: "Open around the clock." };
  mocks.update.mockResolvedValue(updated);
  render(<AdminRoomManager />);

  await screen.findByRole("heading", { name: "Library West" });
  fireEvent.click(screen.getByRole("button", { name: "Edit Library West" }));
  expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe(
    "Library West",
  );
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "Open around the clock." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

  await waitFor(() =>
    expect(mocks.update).toHaveBeenCalledWith(activeRoom.id, {
      name: "Library West",
      description: "Open around the clock.",
      category: "library",
      latitude: 29.6513,
      longitude: -82.3429,
    }),
  );
  expect(await screen.findByText("Updated Library West.")).toBeDefined();
});

test("requires confirmation before archiving a room", async () => {
  mocks.archive.mockResolvedValue({ ...activeRoom, status: "archived" });
  render(<AdminRoomManager />);

  await screen.findByRole("heading", { name: "Library West" });
  fireEvent.click(screen.getByRole("button", { name: "Archive Library West" }));
  expect(screen.getByRole("dialog")).toBeDefined();
  expect(mocks.archive).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(mocks.archive).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Archive Library West" }));
  fireEvent.click(screen.getByRole("button", { name: "Archive room" }));

  await waitFor(() =>
    expect(mocks.archive).toHaveBeenCalledWith(activeRoom.id),
  );
  expect(await screen.findByText("Archived Library West.")).toBeDefined();
  expect(
    screen.queryByRole("button", { name: "Archive Library West" }),
  ).toBeNull();
});

test("shows the protected-page message to a non-admin", async () => {
  mocks.list.mockRejectedValue(
    new ApiRequestError("You are not allowed to do this.", 403, "FORBIDDEN"),
  );
  render(<AdminRoomManager />);

  expect(
    await screen.findByRole("heading", { name: "Not authorized" }),
  ).toBeDefined();
  expect(screen.getByRole("alert").textContent).toMatch(/only available/i);
  expect(
    screen.getByRole("link", { name: /return to admin sign in/i }),
  ).toHaveProperty("href", expect.stringContaining("/admin/login"));
});
