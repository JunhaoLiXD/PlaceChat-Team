import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { Activity, StrictMode } from "react";
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

const router = vi.hoisted(() => ({ push: vi.fn() }));
const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  signInAnonymously: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

vi.mock("@/lib/supabase", () => ({
  getSupabaseBrowserClient: () => ({ auth }),
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
const { RoomScreen } = await import("@/components/room-screen");

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
const pendingResponses = new Set<(response: Response) => void>();

beforeEach(() => {
  channel.status = "connecting";
  router.push.mockReset();
  auth.getSession.mockResolvedValue({
    data: {
      session: {
        access_token: "test-access-token",
        user: { id: "persisted-session-id" },
      },
    },
    error: null,
  });
  auth.signInAnonymously.mockReset();
  auth.signOut.mockReset();
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/api/v1/rooms")) return json([room]);
    if (url.endsWith("/join")) {
      return json({
        room: { id: room.id, name: room.name, description: "" },
        nickname: "Quiet Otter",
      });
    }
    if (url.endsWith("/messages") && (!init?.method || init.method === "GET")) {
      return json([]);
    }
    if (url.endsWith("/messages") && init?.method === "POST") {
      const { body } = JSON.parse(String(init.body)) as { body: string };
      return json(message("sent-1", body, "Quiet Otter"), 201);
    }
    return json({ status: "ok" });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(async () => {
  cleanup();
  // Release deferred requests even after a failed assertion, so queued room
  // operations cannot leak into the next test.
  await act(async () => {
    for (const resolve of pendingResponses) resolve(json({}, 503));
  });
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function requestTo(path: string) {
  const call = fetchMock.mock.calls.find(([input]) =>
    String(input).endsWith(path),
  );
  expect(call).toBeDefined();
  return call![1]!;
}

function requestsTo(path: string) {
  return fetchMock.mock.calls.filter(([input]) => String(input).endsWith(path));
}

function deferResponse() {
  let finish!: (value: Response) => void;
  const promise = new Promise<Response>((done) => {
    finish = done;
  });
  const resolve = (value: Response) => {
    pendingResponses.delete(resolve);
    finish(value);
  };
  pendingResponses.add(resolve);
  return { promise, resolve };
}

async function rejoinActivityWithDraft() {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  const page = (mode: "visible" | "hidden") => (
    <Activity mode={mode}>
      <ChatRoom room={room} />
    </Activity>
  );
  const { rerender } = render(page("visible"));
  await screen.findByText(/you are/i);
  const input = screen.getByLabelText("Message Library West");
  fireEvent.change(input, { target: { value: "saved draft" } });
  expect(screen.getByRole("button", { name: "Send" })).toHaveProperty(
    "disabled",
    false,
  );
  rerender(page("hidden"));
  await act(() => vi.advanceTimersByTimeAsync(61_000));
  expect(requestsTo("/heartbeat")).toHaveLength(0);

  const rejoin = deferResponse();
  fetchMock.mockReturnValueOnce(rejoin.promise);
  await act(async () => {
    rerender(page("visible"));
  });
  return { input, rejoin };
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
  const post = fetchMock.mock.calls.find(
    ([input, init]) =>
      String(input).endsWith(`/api/v1/rooms/${room.id}/messages`) &&
      init?.method === "POST",
  )![1]!;
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

test("tells the participant when the connection is lost and restored", async () => {
  channel.status = "subscribed";
  const { rerender } = render(<ChatRoom room={room} />);
  expect(screen.queryByTestId("connection-banner")).toBeNull();
  await screen.findByText(/you are/i);

  channel.status = "error";
  rerender(<ChatRoom room={room} />);
  expect(screen.getByTestId("connection-banner").textContent).toBe(
    "Connection lost, reconnecting…",
  );

  channel.status = "subscribed";
  rerender(<ChatRoom room={room} />);
  expect(screen.getByTestId("connection-banner").textContent).toBe(
    "Reconnected",
  );
  expect(requestsTo("/join")).toHaveLength(1);
  expect(requestsTo("/leave")).toHaveLength(0);
  expect(auth.signOut).not.toHaveBeenCalled();
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

test.each([
  ["the Leave button", () => screen.getByRole("button", { name: "Leave" })],
  ["the back link", () => screen.getByRole("link", { name: /all rooms/i })],
])(
  "%s leaves the room with the token, then returns to the list",
  async (_name, control) => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    render(<ChatRoom room={room} />);
    await screen.findByText(/you are/i);

    await act(async () => {
      fireEvent.click(control());
    });

    expect(router.push).toHaveBeenCalledWith("/");
    const leave = requestTo(`/api/v1/rooms/${room.id}/leave`);
    expect(leave.method).toBe("POST");
    expect(new Headers(leave.headers).get("Authorization")).toBe(
      "Bearer test-access-token",
    );
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(requestsTo("/heartbeat")).toHaveLength(0);
    expect(auth.signOut).not.toHaveBeenCalled();
  },
);

test("returns to the list even if leaving fails", async () => {
  render(<ChatRoom room={room} />);
  await screen.findByText(/you are/i);
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

  fireEvent.click(screen.getByRole("button", { name: "Leave" }));

  await waitFor(() => expect(router.push).toHaveBeenCalledWith("/"));
});

test("count updates do not rejoin or reload history", async () => {
  const { rerender } = render(<ChatRoom room={room} />);
  await screen.findByText(/you are/i);
  await act(async () => {
    rerender(<ChatRoom room={{ ...room, participant_count: 2 }} />);
  });

  expect(screen.getByText("2 people here")).toBeDefined();
  expect(requestsTo("/join")).toHaveLength(1);
  expect(requestsTo("/messages")).toHaveLength(1);
  expect(requestsTo("/leave")).toHaveLength(0);
});

test("refresh and tab reopening rejoin the URL with persisted auth and clean up heartbeats", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  const first = render(<RoomScreen roomId={room.id} />);
  expect((await screen.findByText(/you are/i)).textContent).toContain(
    "Quiet Otter",
  );
  await act(() => vi.advanceTimersByTimeAsync(15_000));
  expect(requestsTo("/heartbeat")).toHaveLength(1);

  window.dispatchEvent(new Event("beforeunload"));
  window.dispatchEvent(new Event("pagehide"));
  first.unmount();
  await act(() => vi.advanceTimersByTimeAsync(30_000));
  expect(requestsTo("/heartbeat")).toHaveLength(1);
  expect(requestsTo("/leave")).toHaveLength(0);

  render(<RoomScreen roomId={room.id} />);
  expect((await screen.findByText(/you are/i)).textContent).toContain(
    "Quiet Otter",
  );
  await act(() => vi.advanceTimersByTimeAsync(15_000));
  expect(requestsTo("/heartbeat")).toHaveLength(2);
  expect(requestsTo(`/rooms/${room.id}/join`)).toHaveLength(2);
  for (const [, init] of requestsTo("/join")) {
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      "Bearer test-access-token",
    );
  }
  expect(auth.getSession).toHaveBeenCalled();
  expect(auth.signInAnonymously).not.toHaveBeenCalled();
  expect(auth.signOut).not.toHaveBeenCalled();
  expect(requestsTo("/leave")).toHaveLength(0);
});

test("StrictMode cleanup leaves only one heartbeat and never sends Leave", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  const page = render(
    <StrictMode>
      <ChatRoom room={room} />
    </StrictMode>,
  );
  await screen.findByText(/you are/i);
  await act(() => vi.advanceTimersByTimeAsync(15_000));
  expect(requestsTo("/heartbeat")).toHaveLength(1);
  expect(requestsTo("/messages")).toHaveLength(1);
  page.unmount();
  await act(() => vi.advanceTimersByTimeAsync(30_000));
  expect(requestsTo("/heartbeat")).toHaveLength(1);
  expect(requestsTo("/leave")).toHaveLength(0);
});

test("ignores a late join from a closed page without loading its history", async () => {
  const oldJoin = deferResponse();
  fetchMock.mockReturnValueOnce(oldJoin.promise);
  const first = render(<ChatRoom room={room} />);
  await waitFor(() => expect(requestsTo("/join")).toHaveLength(1));
  first.unmount();
  fetchMock.mockResolvedValueOnce(json({ room, nickname: "Calm Fox" }));
  render(<ChatRoom room={room} />);
  await act(async () => {
    oldJoin.resolve(json({ room, nickname: "Quiet Otter" }));
  });
  await screen.findByText("Calm Fox");
  expect(screen.queryByText("Quiet Otter")).toBeNull();
  expect(requestsTo("/messages")).toHaveLength(1);
  expect(requestsTo("/leave")).toHaveLength(0);
});

test("a kept-alive room waits for its rejoin before restarting one heartbeat", async () => {
  const { input, rejoin } = await rejoinActivityWithDraft();
  expect(requestsTo("/join")).toHaveLength(2);
  expect(input).toHaveProperty("value", "saved draft");
  expect(screen.getByRole("button", { name: "Send" })).toHaveProperty(
    "disabled",
    true,
  );
  await act(async () => {
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
    fireEvent.submit(input.closest("form")!);
  });
  expect(
    requestsTo("/messages").filter(([, init]) => init?.method === "POST"),
  ).toHaveLength(0);
  await act(() => vi.advanceTimersByTimeAsync(15_000));
  expect(requestsTo("/heartbeat")).toHaveLength(0);
  await act(async () => {
    rejoin.resolve(json({ room, nickname: "Calm Fox" }));
  });
  expect(screen.getByText("Calm Fox")).toBeDefined();
  expect(screen.getByRole("button", { name: "Send" })).toHaveProperty(
    "disabled",
    false,
  );
  await act(async () => {
    fireEvent.submit(input.closest("form")!);
  });
  expect(
    requestsTo("/messages").filter(([, init]) => init?.method === "POST"),
  ).toHaveLength(1);
  await act(() => vi.advanceTimersByTimeAsync(15_000));
  expect(requestsTo("/heartbeat")).toHaveLength(1);
  expect(requestsTo("/leave")).toHaveLength(0);
});

test("a failed Activity rejoin shows its error and keeps the preserved draft unsendable", async () => {
  const { input, rejoin } = await rejoinActivityWithDraft();
  await act(async () => {
    rejoin.resolve(
      json({ error: { message: "This visit could not join." } }, 503),
    );
  });

  expect(screen.getByRole("alert").textContent).toBe(
    "This visit could not join.",
  );
  expect(screen.queryByText("Quiet Otter")).toBeNull();
  expect(screen.getByRole("button", { name: "Send" })).toHaveProperty(
    "disabled",
    true,
  );
  await act(async () => {
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
    fireEvent.submit(input.closest("form")!);
  });
  expect(
    requestsTo("/messages").filter(([, init]) => init?.method === "POST"),
  ).toHaveLength(0);
  await act(() => vi.advanceTimersByTimeAsync(30_000));
  expect(requestsTo("/heartbeat")).toHaveLength(0);
  expect(requestsTo("/leave")).toHaveLength(0);
});

test.each([
  ["Leave", () => screen.getByRole("button", { name: "Leave" })],
  ["All rooms/Back", () => screen.getByRole("link", { name: /all rooms/i })],
])(
  "%s navigates immediately during a pending join and ignores its late result",
  async (_name, control) => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const pending = deferResponse();
    fetchMock.mockReturnValueOnce(pending.promise);
    await act(async () => {
      render(<ChatRoom room={room} />);
    });
    expect(requestsTo("/join")).toHaveLength(1);
    fireEvent.click(control());
    expect(router.push).toHaveBeenCalledExactlyOnceWith("/");
    expect(channel.roomId).toBeNull();
    await act(async () => {
      pending.resolve(json({ room, nickname: "Quiet Otter" }));
    });
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/"));
    expect(requestsTo("/leave")).toHaveLength(1);
    expect(requestsTo("/messages")).toHaveLength(0);
    expect(screen.queryByText("Quiet Otter")).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(requestsTo("/heartbeat")).toHaveLength(0);
  },
);

test.each([
  ["join", 200, "remount"],
  ["leave", 200, "remount"],
  ["leave", 503, "remount"],
  ["join", 200, "Activity"],
  ["leave", 200, "Activity"],
] as const)(
  "old %s pending (cleanup HTTP %i, %s return) cannot end the new membership",
  async (pendingStage, cleanupStatus, revisit) => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const oldJoin = deferResponse();
    const oldLeave = deferResponse();
    let joined = false;
    let joinCount = 0;
    const operations: string[] = [];
    const defaultFetch = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (url, init) => {
      if (String(url).endsWith("/join")) {
        const index = ++joinCount;
        operations.push(`join ${index}`);
        const response =
          index === 1 && pendingStage === "join"
            ? await oldJoin.promise
            : json({
                room,
                nickname: index === 1 ? "Quiet Otter" : "Calm Fox",
              });
        joined = true;
        return response;
      }
      if (String(url).endsWith("/leave")) {
        operations.push("leave");
        const response = await oldLeave.promise;
        joined = false;
        return response;
      }
      return defaultFetch(url, init);
    });

    const page = (mode: "visible" | "hidden") => (
      <Activity mode={mode}>
        <ChatRoom room={room} />
      </Activity>
    );
    const first = render(page("visible"));
    await act(async () => {});
    if (pendingStage === "leave") await screen.findByText(/you are/i);
    fireEvent.click(screen.getByRole("button", { name: "Leave" }));
    expect(router.push).toHaveBeenCalledExactlyOnceWith("/");
    if (revisit === "Activity") first.rerender(page("hidden"));
    else first.unmount();
    await act(async () => {
      if (revisit === "Activity") first.rerender(page("visible"));
      else render(page("visible"));
    });
    expect(requestsTo("/join")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Leave" })).toHaveProperty(
      "disabled",
      false,
    );
    expect(screen.getByRole("button", { name: "Send" })).toHaveProperty(
      "disabled",
      true,
    );

    await act(async () => {
      oldJoin.resolve(json({ room, nickname: "Quiet Otter" }));
    });
    expect(requestsTo("/leave")).toHaveLength(1);
    expect(requestsTo("/join")).toHaveLength(1);
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(requestsTo("/heartbeat")).toHaveLength(0);
    await act(async () => {
      oldLeave.resolve(json({ status: "ok" }, cleanupStatus));
    });

    expect(operations).toEqual(["join 1", "leave", "join 2"]);
    expect(joined).toBe(true);
    expect(screen.getByText("Calm Fox")).toBeDefined();
    expect(screen.queryByText("Quiet Otter")).toBeNull();
    expect(router.push).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(15_000));
    expect(requestsTo("/heartbeat")).toHaveLength(1);
    expect(auth.signOut).not.toHaveBeenCalled();
  },
);
