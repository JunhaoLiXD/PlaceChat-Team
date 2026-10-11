import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import Home from "@/app/page";

test("home page shows the PlaceChat heading", () => {
  render(<Home />);
  expect(
    screen.getByRole("heading", { level: 1, name: "PlaceChat" }),
  ).toBeDefined();
});
