import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { Activity } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ChatRoom, MessageFeed } from "@/components/chat-room";
import { MOCK_ROOMS } from "@/lib/mock-data";
import type { ChatMessage } from "@/lib/placechat-types";

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const room = MOCK_ROOMS.find((candidate) => candidate.id === "library-west")!;

beforeEach(() => router.push.mockReset());
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

test("Leave returns to the room list in mock mode", async () => {
  render(<ChatRoom room={room} />);
  await screen.findByText(/you are/i);

  fireEvent.click(screen.getByRole("button", { name: "Leave" }));

  await waitFor(() => expect(router.push).toHaveBeenCalledWith("/"));
});

test("Leave works again after returning to a room the router kept alive", async () => {
  // Next.js keeps a visited page in a hidden <Activity> and shows it again on return.
  const page = (mode: "visible" | "hidden") => (
    <Activity mode={mode}>
      <ChatRoom room={room} />
    </Activity>
  );
  const { rerender } = render(page("visible"));
  await screen.findByText(/you are/i);
  fireEvent.click(screen.getByRole("button", { name: "Leave" }));
  await waitFor(() => expect(router.push).toHaveBeenCalledTimes(1));

  rerender(page("hidden"));
  rerender(page("visible"));

  const leave = await screen.findByRole("button", { name: "Leave" });
  expect(leave).toHaveProperty("disabled", false);
  fireEvent.click(leave);
  await waitFor(() => expect(router.push).toHaveBeenCalledTimes(2));
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
  expect(
    within(message.closest("article")!).queryByRole("button", {
      name: "Report",
    }),
  ).toBeNull();

  await waitFor(() => expect(input).toHaveProperty("value", ""));
});

test("reports another participant's message with an optional reason", async () => {
  render(<ChatRoom room={room} />);
  await screen.findByText(/you are/i);

  const message = screen.getByText("Has anyone found a quiet corner nearby?");
  const bubble = within(message.closest("article")!);
  fireEvent.click(bubble.getByRole("button", { name: "Report" }));
  fireEvent.change(bubble.getByLabelText(/reason/i), {
    target: { value: "harassment" },
  });
  fireEvent.click(bubble.getByRole("button", { name: "Submit report" }));

  expect((await bubble.findByRole("status")).textContent).toBe(
    "Report submitted",
  );
  expect(bubble.queryByRole("button", { name: "Report" })).toBeNull();
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

test("missed messages inserted before an existing own message do not pull a reader down", async () => {
  const first: ChatMessage = {
    id: "first",
    room_id: room.id,
    nickname: "Calm Fox",
    body: "First",
    created_at: "2026-10-13T13:42:00-04:00",
  };
  const own = {
    ...first,
    id: "own",
    body: "Mine",
    created_at: "2026-10-13T13:44:00-04:00",
  };
  const missed = {
    ...first,
    id: "missed",
    body: "Missed",
    created_at: "2026-10-13T13:43:00-04:00",
  };
  const ids = new Set([own.id]);
  const view = render(
    <MessageFeed messages={[first, own]} ownMessageIds={ids} />,
  );
  const scrollRegion = screen.getByTestId("message-scroll-region");
  Object.defineProperties(scrollRegion, {
    clientHeight: { configurable: true, value: 200 },
    scrollHeight: { configurable: true, value: 1000 },
    scrollTop: { configurable: true, value: 100 },
  });
  fireEvent.scroll(scrollRegion);
  view.rerender(
    <MessageFeed messages={[first, missed, own]} ownMessageIds={ids} />,
  );
  expect(
    await screen.findByRole("button", { name: /1 new message/i }),
  ).toBeDefined();
  expect(scrollRegion.scrollTop).toBe(100);
});

test("regression: recovered own history, including another tab's messages, preserves scrolling", async () => {
  vi.useFakeTimers();
  try {
    const first: ChatMessage = {
      id: "first",
      room_id: room.id,
      nickname: "Calm Fox",
      body: "First",
      created_at: "2026-10-13T13:42:00-04:00",
    };
    const history = {
      ...first,
      id: "other-tab",
      body: "My history",
      is_mine: true,
    };
    const view = render(
      <MessageFeed messages={[first]} ownMessageIds={new Set()} />,
    );
    const region = screen.getByTestId("message-scroll-region");
    const scrollTo = vi.fn();
    Object.defineProperties(region, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, value: 100 },
      scrollTo: { configurable: true, value: scrollTo },
    });
    fireEvent.scroll(region);
    view.rerender(
      <MessageFeed messages={[first, history]} ownMessageIds={new Set()} />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(16);
    });
    expect(scrollTo).not.toHaveBeenCalled();
    expect(region.scrollTop).toBe(100);
    expect(
      screen.getByRole("button", { name: /1 new message/i }),
    ).toBeDefined();
    expect(
      screen.getByText("My history").closest("article")?.dataset.ownMessage,
    ).toBe("true");
  } finally {
    vi.useRealTimers();
  }
});

test.each(["response first", "live first"])(
  "this visit's actual submission scrolls to the message (%s)",
  async (order) => {
    vi.useFakeTimers();
    try {
      const first: ChatMessage = {
        id: "first",
        room_id: room.id,
        nickname: "Calm Fox",
        body: "First",
        created_at: "2026-10-13T13:42:00-04:00",
      };
      const own = { ...first, id: "submitted", body: "Submitted" };
      const view = render(
        <MessageFeed messages={[first]} ownMessageIds={new Set()} />,
      );
      const region = screen.getByTestId("message-scroll-region");
      const scrollTo = vi.fn();
      Object.defineProperties(region, {
        clientHeight: { configurable: true, value: 200 },
        scrollHeight: { configurable: true, value: 1000 },
        scrollTop: { configurable: true, value: 100 },
        scrollTo: { configurable: true, value: scrollTo },
      });
      fireEvent.scroll(region);
      if (order === "live first") {
        view.rerender(
          <MessageFeed messages={[first, own]} ownMessageIds={new Set()} />,
        );
        expect(
          screen.getByRole("button", { name: /1 new message/i }),
        ).toBeDefined();
      }
      view.rerender(
        <MessageFeed
          messages={[first, own]}
          ownMessageIds={new Set([own.id])}
        />,
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(16);
      });
      expect(scrollTo).toHaveBeenCalledExactlyOnceWith({
        top: 1000,
        behavior: "smooth",
      });
      expect(screen.queryByRole("button", { name: /new message/i })).toBeNull();
      expect(
        screen.getByText("Submitted").closest("article")?.dataset.ownMessage,
      ).toBe("true");
    } finally {
      vi.useRealTimers();
    }
  },
);

test("Activity cleanup cancels the previous visit's pending scroll", async () => {
  vi.useFakeTimers();
  try {
    const first: ChatMessage = {
      id: "first",
      room_id: room.id,
      nickname: "Calm Fox",
      body: "First",
      created_at: "2026-10-13T13:42:00-04:00",
    };
    const own = { ...first, id: "submitted", body: "Submitted", is_mine: true };
    const page = (
      mode: "visible" | "hidden",
      messages: ChatMessage[],
      submitted = new Set<string>(),
    ) => (
      <Activity mode={mode}>
        <MessageFeed messages={messages} ownMessageIds={submitted} />
      </Activity>
    );
    const view = render(page("visible", [first]));
    const region = screen.getByTestId("message-scroll-region");
    const scrollTo = vi.fn();
    Object.defineProperties(region, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, value: 100 },
      scrollTo: { configurable: true, value: scrollTo },
    });
    fireEvent.scroll(region);
    view.rerender(page("visible", [first, own], new Set([own.id])));
    view.rerender(page("hidden", [first, own]));
    view.rerender(page("visible", [first, own]));
    fireEvent.scroll(region);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(16);
    });
    expect(scrollTo).not.toHaveBeenCalled();
    expect(region.scrollTop).toBe(100);
  } finally {
    vi.useRealTimers();
  }
});
