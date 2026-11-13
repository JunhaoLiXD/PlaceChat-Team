import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AdminLoginForm } from "@/components/admin-login-form";
import { ApiRequestError } from "@/lib/placechat-api";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  listRooms: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));

vi.mock("@/lib/admin-auth", () => ({
  signInWithPassword: mocks.signIn,
  signOutAdmin: mocks.signOut,
}));

vi.mock("@/lib/placechat-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/placechat-api")>()),
  listAdminRooms: mocks.listRooms,
}));

beforeEach(() => {
  vi.resetAllMocks();
  mocks.signIn.mockResolvedValue({});
  mocks.signOut.mockResolvedValue(undefined);
  mocks.listRooms.mockResolvedValue([]);
});

afterEach(cleanup);

function submitCredentials() {
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: " admin@example.edu " },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "secret-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

test("signs in, verifies administrator access, and opens room management", async () => {
  render(<AdminLoginForm />);

  submitCredentials();

  await waitFor(() => {
    expect(mocks.signIn).toHaveBeenCalledWith(
      "admin@example.edu",
      "secret-password",
    );
  });
  expect(mocks.listRooms).toHaveBeenCalledOnce();
  expect(mocks.replace).toHaveBeenCalledWith("/admin/rooms");
});

test("shows a clear not-authorized message and clears a non-admin session", async () => {
  mocks.listRooms.mockRejectedValue(
    new ApiRequestError("You are not allowed to do this.", 403, "FORBIDDEN"),
  );
  render(<AdminLoginForm />);

  submitCredentials();

  expect((await screen.findByRole("alert")).textContent).toMatch(
    /not authorized/i,
  );
  expect(mocks.signOut).toHaveBeenCalledOnce();
  expect(mocks.replace).not.toHaveBeenCalled();
});

test("does not expose the authentication provider's error details", async () => {
  mocks.signIn.mockRejectedValue(new Error("User lookup details"));
  render(<AdminLoginForm />);

  submitCredentials();

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toMatch(/sign-in failed/i);
  expect(alert.textContent).not.toMatch(/user lookup/i);
});
