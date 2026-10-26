import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { ChatMessage, RoomSummary } from "@/lib/placechat-types";
import type { RoomChannelStatus } from "@/lib/use-room-channel";

// Configure a real backend before any module reads the public config.
vi.hoisted(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example.test";
  process.env.NEXT_PUBLIC_USE_MOCKS = "false";
});

const channel = vi.hoisted(() => ({
  status: "connecting" as RoomChannelStatus,
  roomId: undefined as string | null | undefined,
  onMessage: (() => {}) as (message: ChatMessage) => void,
}));

vi.mock("@/lib/session", () => ({
  getAccessToken: vi.fn().mockResolvedValue("test-access-token"),
}));

vi.mock("@/lib/use-room-channel", () => ({
  useRoomChannel: (
    roomId: string | null,
    onMessage: (message: ChatMessage) => void,
  ) => {
    channel.roomId = roomId;
    channel.onMessage = onMessage;
    return channel.status;
  },
}));

const { ChatRoom } = await import("@/components/chat-room");

const room: RoomSummary = {
  id: "8f0c2b1e-0000-4000-8000-000000000001",
  name: "Library West",
  description: "Quiet floors.",
  category: "library",
  latitude: 29.65,
  longitude: -82.34,
  participant_count: 0,
};

function message(id: string, body: string, nickname = "Calm Fox") {
  return {
    id,
    room_id: room.id,
    nickname,
    body,
    created_at: "2026-10-21T16:00:00Z",
  } satisfies ChatMessage;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  channel.status = "connecting";
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/join")) {
      return json({
        room: { id: room.id, name: room.name, description: "" },
        nickname: "Quiet Otter",
      });
    }
    if (url.endsWith("/messages") && init?.method === "POST") {
      const { body } = JSON.parse(String(init.body)) as { body: string };
      return json(message("sent-1", body, "Quiet Otter"), 201);
    }
    return json({ status: "ok" });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function requestTo(path: string) {
  const call = fetchMock.mock.calls.find(([input]) =>
    String(input).endsWith(path),
  );
  expect(call).toBeDefined();
  return call![1]!;
}

test("joins with the session token and starts without demo messages", async () => {
  render(<ChatRoom room={room} />);

  expect((await screen.findByText(/you are/i)).textContent).toContain(
    "Quiet Otter",
  );
  const join = requestTo(`/api/v1/rooms/${room.id}/join`);
  expect(join.method).toBe("POST");
  expect(new Headers(join.headers).get("Authorization")).toBe(
    "Bearer test-access-token",
  );
  expect(screen.queryByText("Bright Heron")).toBeNull();
  expect(channel.roomId).toBe(room.id);
});

test("sends through the API and shows the message once, even after its broadcast", async () => {
  render(<ChatRoom room={room} />);
  await screen.findByText(/you are/i);

  const input = screen.getByLabelText("Message Library West");
  fireEvent.change(input, { target: { value: "  hello there  " } });
  fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

  const sent = await screen.findByText("hello there", { selector: "p" });
  expect(sent.closest("article")?.dataset.ownMessage).toBe("true");
  const post = requestTo(`/api/v1/rooms/${room.id}/messages`);
  expect(JSON.parse(String(post.body))).toEqual({ body: "hello there" });
  expect(new Headers(post.headers).get("Authorization")).toBe(
    "Bearer test-access-token",
  );

  act(() => channel.onMessage(message("sent-1", "hello there", "Quiet Otter")));
  expect(screen.getAllByText("hello there", { selector: "p" })).toHaveLength(1);
});

test("shows messages from other people as they arrive", async () => {
  render(<ChatRoom room={room} />);
  await screen.findByText(/you are/i);

  act(() => channel.onMessage(message("other-1", "anyone at the desk?")));

  const incoming = await screen.findByText("anyone at the desk?", {
    selector: "p",
  });
  expect(incoming.closest("article")?.dataset.ownMessage).toBe("false");
});

test("the status badge follows the realtime channel", async () => {
  const { rerender } = render(<ChatRoom room={room} />);
  expect(screen.getByRole("status").textContent).toBe("Connecting…");

  channel.status = "subscribed";
  rerender(<ChatRoom room={room} />);
  expect(screen.getByRole("status").textContent).toBe("Connected");

  channel.status = "error";
  rerender(<ChatRoom room={room} />);
  expect(screen.getByRole("status").textContent).toBe("Reconnecting…");
});

test("shows the API's message when sending is rejected", async () => {
  render(<ChatRoom room={room} />);
  await screen.findByText(/you are/i);
  fetchMock.mockResolvedValueOnce(
    json(
      {
        error: {
          code: "RATE_LIMITED",
          message: "You are sending messages too fast. Try again in 7 seconds.",
          retry_after: 7,
        },
      },
      429,
    ),
  );

  const input = screen.getByLabelText("Message Library West");
  fireEvent.change(input, { target: { value: "spam" } });
  fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

  expect((await screen.findByRole("alert")).textContent).toMatch(/too fast/i);
  await waitFor(() => expect(input).toHaveProperty("value", "spam"));
});

test("shows the API's message when the room cannot be joined", async () => {
  fetchMock.mockResolvedValueOnce(
    json(
      {
        error: {
          code: "ROOM_NOT_FOUND",
          message: "This room does not exist or has been closed.",
        },
      },
      404,
    ),
  );

  render(<ChatRoom room={room} />);

  expect(await screen.findByText(/has been closed/i)).toBeDefined();
});
