import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import Home from "@/app/page";

afterEach(cleanup);

test("home page shows active room cards", async () => {
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
