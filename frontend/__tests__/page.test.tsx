import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import Home from "@/app/page";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

test("home page shows active room cards", async () => {
  vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "true");
  render(<Home />);
  expect(
    screen.getByRole("heading", { level: 1, name: /find your place/i }),
  ).toBeDefined();

  expect(
    await screen.findByRole("heading", { level: 2, name: "Library West" }),
  ).toBeDefined();
  expect(screen.getByText("24 people here")).toBeDefined();
  expect(
    screen.getByRole("link", { name: /join library west/i }),
  ).toHaveProperty("href", expect.stringContaining("/rooms/library-west"));
});

test("home page shows the API error when the configured backend is unavailable", async () => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");
  vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "false");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
  );

  render(<Home />);

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toMatch(/server is unavailable/i);
  expect(screen.getByRole("button", { name: /try again/i })).toBeDefined();
});
