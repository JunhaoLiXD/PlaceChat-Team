import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { ChatRoom, MessageFeed } from "@/components/chat-room";
import { MOCK_ROOMS } from "@/lib/mock-data";
import type { ChatMessage } from "@/lib/placechat-types";

const room = MOCK_ROOMS.find((candidate) => candidate.id === "library-west")!;

afterEach(cleanup);

test("room page shows identity, safety reminder, and messages", async () => {
  render(<ChatRoom room={room} />);

  expect(screen.getByRole("heading", { name: "Library West" })).toBeDefined();
  expect((await screen.findByText(/you are/i)).textContent).toContain(
    "Quiet Otter",
  );
  expect(screen.getByText(/keep it kind/i)).toBeDefined();
  expect(screen.getAllByText("Bright Heron").length).toBeGreaterThan(0);
});

test("whitespace-only and over-limit messages cannot be sent", async () => {
  render(<ChatRoom room={room} />);
  await screen.findByText(/you are/i);

  const input = screen.getByLabelText("Message Library West");
  const sendButton = screen.getByRole("button", { name: /send/i });

  fireEvent.change(input, { target: { value: "   " } });
  expect(sendButton).toHaveProperty("disabled", true);

  fireEvent.change(input, { target: { value: "x".repeat(501) } });
  expect(sendButton).toHaveProperty("disabled", true);
  expect(screen.getByRole("alert").textContent).toMatch(
    /up to 500 characters/i,
  );
});

test("Enter sends trimmed plain text and marks it as the participant's own", async () => {
  render(<ChatRoom room={room} />);
  await screen.findByText(/you are/i);

  const input = screen.getByLabelText("Message Library West");
  fireEvent.change(input, {
    target: { value: "  <img src=x onerror=alert(1)> https://example.com  " },
  });
  fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

  const message = await screen.findByText(
    "<img src=x onerror=alert(1)> https://example.com",
    { selector: "p" },
  );
  expect(message.closest("article")?.dataset.ownMessage).toBe("true");
  expect(message.querySelector("img")).toBeNull();
  expect(message.querySelector("a")).toBeNull();

  await waitFor(() => expect(input).toHaveProperty("value", ""));
});

test("a reader who scrolled up gets a new-message button", async () => {
  const firstMessage: ChatMessage = {
    id: "first",
    room_id: room.id,
    nickname: "Calm Fox",
    body: "First message",
    created_at: "2026-10-13T13:42:00-04:00",
  };
  const incomingMessage: ChatMessage = {
    ...firstMessage,
    id: "incoming",
    body: "Incoming message",
  };

  const { rerender } = render(
    <MessageFeed messages={[firstMessage]} ownMessageIds={new Set()} />,
  );
  const scrollRegion = screen.getByTestId("message-scroll-region");
  Object.defineProperties(scrollRegion, {
    clientHeight: { configurable: true, value: 200 },
    scrollHeight: { configurable: true, value: 1000 },
    scrollTop: { configurable: true, value: 100 },
  });
  fireEvent.scroll(scrollRegion);

  rerender(
    <MessageFeed
      messages={[firstMessage, incomingMessage]}
      ownMessageIds={new Set()}
    />,
  );

  expect(
    await screen.findByRole("button", { name: /1 new message/i }),
  ).toBeDefined();
});
