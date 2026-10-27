import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { RoomScreen } from "@/components/room-screen";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

test("opens a room from the active-rooms list", async () => {
  vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "true");

  render(<RoomScreen roomId="library-west" />);

  expect(
    await screen.findByRole("heading", { name: "Library West" }),
  ).toBeDefined();
});

test("shows a clear message for an unknown or closed room", async () => {
  vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "true");

  render(<RoomScreen roomId="no-such-room" />);

  expect(
    await screen.findByRole("heading", { name: "Room not found" }),
  ).toBeDefined();
  expect(
    screen.getByRole("link", { name: /back to all rooms/i }),
  ).toBeDefined();
});

test("shows the API error when the room list cannot load", async () => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");
  vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "false");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
  );

  render(<RoomScreen roomId="library-west" />);

  expect((await screen.findByRole("alert")).textContent).toMatch(
    /server is unavailable/i,
  );
});
