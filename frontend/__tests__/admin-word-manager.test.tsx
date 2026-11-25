import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AdminWordManager } from "@/components/admin-word-manager";
import { ApiRequestError } from "@/lib/placechat-api";
import type { BlockedWord } from "@/lib/placechat-types";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  add: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("@/lib/placechat-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/placechat-api")>()),
  listBlockedWords: mocks.list,
  addBlockedWord: mocks.add,
  deleteBlockedWord: mocks.remove,
}));

function word(id: string, text: string): BlockedWord {
  return { id, word: text, created_at: "2026-11-19T12:00:00Z" };
}

const zebra = word("11111111-1111-4111-8111-111111111111", "zebra");
const apple = word("22222222-2222-4222-8222-222222222222", "apple");

beforeEach(() => {
  vi.resetAllMocks();
  mocks.list.mockResolvedValue([zebra, apple]);
  mocks.remove.mockResolvedValue(undefined);
});

afterEach(cleanup);

function listedWords() {
  return within(screen.getByRole("list"))
    .getAllByRole("listitem")
    .map((item) => item.querySelector("span")?.textContent);
}

test("lists the blocked words in alphabetical order", async () => {
  render(<AdminWordManager />);

  await screen.findByText("apple");
  expect(listedWords()).toEqual(["apple", "zebra"]);
  expect(screen.getByText("2 words")).toBeTruthy();
});

test("adds a word, keeps the list sorted, and clears the input", async () => {
  mocks.add.mockResolvedValue(
    word("33333333-3333-4333-8333-333333333333", "badword"),
  );
  render(<AdminWordManager />);
  await screen.findByText("apple");

  const input = screen.getByLabelText(
    "Add a word or phrase",
  ) as HTMLInputElement;
  fireEvent.change(input, { target: { value: "  BadWord  " } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));

  await screen.findByText("badword");
  expect(mocks.add).toHaveBeenCalledWith("BadWord");
  expect(listedWords()).toEqual(["apple", "badword", "zebra"]);
  expect(input.value).toBe("");
  expect(screen.getByRole("status").textContent).toMatch(/added "badword"/i);
});

test("does not submit an empty or blank word", async () => {
  render(<AdminWordManager />);
  await screen.findByText("apple");

  const add = screen.getByRole("button", { name: "Add" }) as HTMLButtonElement;
  expect(add.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("Add a word or phrase"), {
    target: { value: "   " },
  });
  expect(add.disabled).toBe(true);
  expect(mocks.add).not.toHaveBeenCalled();
});

test("shows the API message when the word is already on the list", async () => {
  mocks.add.mockRejectedValue(
    new ApiRequestError(
      '"apple" is already on the blocked-word list.',
      422,
      "VALIDATION_FAILED",
    ),
  );
  render(<AdminWordManager />);
  await screen.findByText("apple");

  fireEvent.change(screen.getByLabelText("Add a word or phrase"), {
    target: { value: "Apple" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));

  expect((await screen.findByRole("alert")).textContent).toMatch(
    /already on the blocked-word list/,
  );
  expect(listedWords()).toEqual(["apple", "zebra"]);
});

test("removes a word", async () => {
  render(<AdminWordManager />);
  await screen.findByText("apple");

  fireEvent.click(screen.getByRole("button", { name: "Remove apple" }));

  await waitFor(() => expect(listedWords()).toEqual(["zebra"]));
  expect(mocks.remove).toHaveBeenCalledWith(apple.id);
  expect(screen.getByRole("status").textContent).toMatch(/removed "apple"/i);
});

test("shows an empty state when there are no words", async () => {
  mocks.list.mockResolvedValue([]);
  render(<AdminWordManager />);

  expect(await screen.findByText("No blocked words yet.")).toBeTruthy();
});

test("shows not authorized for a non-admin", async () => {
  mocks.list.mockRejectedValue(
    new ApiRequestError("You are not allowed to do this.", 403, "FORBIDDEN"),
  );
  render(<AdminWordManager />);

  expect(
    await screen.findByRole("heading", { name: "Not authorized" }),
  ).toBeTruthy();
});

test("shows a load error and retries", async () => {
  mocks.list
    .mockRejectedValueOnce(
      new ApiRequestError("The server is unavailable. Please try again.", 0),
    )
    .mockResolvedValueOnce([apple]);
  render(<AdminWordManager />);

  expect((await screen.findByRole("alert")).textContent).toMatch(/unavailable/);
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));

  await screen.findByText("apple");
  expect(mocks.list).toHaveBeenCalledTimes(2);
});
