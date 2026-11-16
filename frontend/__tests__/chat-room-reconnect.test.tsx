import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { Activity, StrictMode, type ReactNode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { ChatMessage, RoomSummary } from "@/lib/placechat-types";

type ChannelRecord = {
  topic: string;
  handlers: Map<string, (event: { payload: unknown }) => void>;
  status?: (status: string) => void;
  removed: boolean;
};

const fake = vi.hoisted(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example.test";
  process.env.NEXT_PUBLIC_USE_MOCKS = "false";
  return {
    channels: [] as ChannelRecord[],
    client: {
      auth: {
        getSession: vi.fn(),
        signInAnonymously: vi.fn(),
        signOut: vi.fn(),
      },
      realtime: { setAuth: vi.fn() },
      channel: vi.fn(),
      removeChannel: vi.fn(),
    },
    push: vi.fn(),
  };
});

vi.mock("@/lib/supabase", () => ({
  getSupabaseBrowserClient: () => fake.client,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: fake.push }) }));

const { ChatRoom } = await import("@/components/chat-room");

const room: RoomSummary = {
  id: "room-1",
  name: "Library West",
  description: "Quiet floors.",
  category: "library",
  latitude: 29.65,
  longitude: -82.34,
  participant_count: 2,
};
const otherRoom = { ...room, id: "room-2", name: "Marston" };

function message(id: string, second: number, isMine?: boolean): ChatMessage {
  return {
    id,
    room_id: room.id,
    nickname: "Calm Fox",
    body: id,
    created_at: new Date(Date.UTC(2026, 10, 15, 12, 0, second)).toISOString(),
    ...(isMine === undefined ? {} : { is_mine: isMine }),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

const history =
  vi.fn<(roomId: string, after?: string) => Promise<ChatMessage[]>>();
const send = vi.fn<() => Promise<ChatMessage>>();
const fetchMock = vi.fn<typeof fetch>();
let offline = false;
let successfulHeartbeats = 0;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.resetAllMocks();
  offline = false;
  successfulHeartbeats = 0;
  fake.channels.length = 0;
  fake.client.auth.getSession.mockResolvedValue({
    data: {
      session: {
        access_token: "persisted-token",
        user: { id: "same-session" },
      },
    },
    error: null,
  });
  fake.client.realtime.setAuth.mockResolvedValue(undefined);
  fake.client.removeChannel.mockImplementation(
    async (channel: { record: ChannelRecord }) => {
      channel.record.removed = true;
      return "ok";
    },
  );
  fake.client.channel.mockImplementation((topic: string) => {
    const record: ChannelRecord = {
      topic,
      handlers: new Map(),
      removed: false,
    };
    fake.channels.push(record);
    const channel = {
      record,
      on: (
        _type: string,
        filter: { event: string },
        handler: (event: { payload: unknown }) => void,
      ) => {
        record.handlers.set(filter.event, handler);
        return channel;
      },
      subscribe: (handler: (status: string) => void) => {
        record.status = handler;
        return channel;
      },
    };
    return channel;
  });
  history.mockResolvedValue([message("m1", 1)]);
  send.mockResolvedValue(message("own", 4));
  fetchMock.mockImplementation(async (input, init) => {
    if (offline) throw new TypeError("offline");
    const url = new URL(String(input));
    const roomId = url.pathname.split("/")[4];
    if (url.pathname.endsWith("/join")) {
      return json({
        room: { id: roomId, name: room.name, description: "" },
        nickname: "Backend Otter",
      });
    }
    if (url.pathname.endsWith("/messages")) {
      return init?.method === "POST"
        ? json(await send(), 201)
        : json(
            await history(roomId, url.searchParams.get("after") ?? undefined),
          );
    }
    if (url.pathname.endsWith("/heartbeat")) successfulHeartbeats += 1;
    return json({ status: "ok" });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function currentChannel() {
  return fake.channels.at(-1)!;
}
function emit(state: string, channel = currentChannel()) {
  channel.status?.(state);
}
function live(item: ChatMessage, channel = currentChannel()) {
  channel.handlers.get("message.created")?.({ payload: item });
}
async function settle(action: () => void = () => {}) {
  await act(async () => {
    action();
  });
}
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}
async function mount(
  wrapper: (child: ReactNode) => ReactNode = (child) => child,
  subscribe = true,
) {
  const view = render(wrapper(<ChatRoom room={room} />));
  await settle();
  expect(fake.channels.filter((channel) => !channel.removed)).toHaveLength(1);
  if (subscribe) await settle(() => emit("SUBSCRIBED"));
  return view;
}
function bodies() {
  return Array.from(
    screen.getByRole("list").querySelectorAll("article p"),
    (node) => node.textContent,
  );
}
function heartbeats() {
  return fetchMock.mock.calls.filter(([url]) =>
    String(url).endsWith("/heartbeat"),
  );
}
function joins() {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/join"));
}
function leaves() {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/leave"));
}

test.each([
  ["remount", "Leave"],
  ["remount", "Back"],
  ["Activity", "Leave"],
  ["Activity", "Back"],
])(
  "regression: a delayed Leave cannot cancel membership after a quick return (%s, %s)",
  async (mode, control) => {
    const pendingLeave = deferred<void>();
    const normalFetch = fetchMock.getMockImplementation()!;
    let membershipActive = false;
    let joinStarts = 0;
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input).endsWith("/join")) {
        joinStarts += 1;
        membershipActive = true;
      }
      if (String(input).endsWith("/leave")) {
        await pendingLeave.promise;
        membershipActive = false;
      }
      return normalFetch(input, init);
    });
    const page = (visible: boolean) =>
      mode === "Activity" ? (
        <Activity mode={visible ? "visible" : "hidden"}>
          <ChatRoom room={room} />
        </Activity>
      ) : visible ? (
        <ChatRoom room={room} />
      ) : null;
    const view = render(page(true));
    await settle();
    await settle(() =>
      fireEvent.click(
        control === "Leave"
          ? screen.getByRole("button", { name: "Leave" })
          : screen.getByRole("link", { name: /all rooms/i }),
      ),
    );
    const navigatedBeforeLeave = fake.push.mock.calls.length;
    await settle(() => view.rerender(page(false)));
    await settle(() => view.rerender(page(true)));
    fireEvent.change(screen.getByLabelText("Message Library West"), {
      target: { value: "queued draft" },
    });
    const disabledBeforeLeave = screen
      .getByRole("button", { name: /send/i })
      .hasAttribute("disabled");
    await advance(15_000);
    const heartbeatsBeforeLeave = heartbeats().length;
    const joinsBeforeLeave = joinStarts;
    await settle(() => pendingLeave.resolve());
    expect(membershipActive).toBe(true);
    expect(joinsBeforeLeave).toBe(1);
    expect(joinStarts).toBe(2);
    expect(navigatedBeforeLeave).toBe(1);
    expect(disabledBeforeLeave).toBe(true);
    expect(heartbeatsBeforeLeave).toBe(0);
    expect(screen.getByText("Backend Otter")).toBeDefined();
    await advance(15_000);
    expect(heartbeats()).toHaveLength(1);
  },
);

test.each(["network", "server"])(
  "a failed old Leave releases the same-room queue (%s)",
  async (failure) => {
    const pendingLeave = deferred<void>();
    const normalFetch = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input).endsWith("/leave")) {
        await pendingLeave.promise;
        if (failure === "network") throw new TypeError("cleanup unavailable");
        return json({ error: { message: "Cleanup failed" } }, 500);
      }
      return normalFetch(input, init);
    });
    const first = await mount();
    await settle(() =>
      fireEvent.click(screen.getByRole("link", { name: /all rooms/i })),
    );
    const navigated = fake.push.mock.calls.length;
    first.unmount();
    await mount();
    const startsBeforeFailure = joins().length;
    await settle(() => pendingLeave.resolve());
    expect(navigated).toBe(1);
    expect(startsBeforeFailure).toBe(1);
    expect(joins()).toHaveLength(2);
    expect(screen.getByText("Backend Otter")).toBeDefined();
    await advance(15_000);
    expect(heartbeats()).toHaveLength(1);
  },
);

test.each([false, true])(
  "Leave during a pending initial Join stays immediate and cleans up before returning (join fails: %s)",
  async (failFirstJoin) => {
    const pendingJoin = deferred<void>();
    const normalFetch = fetchMock.getMockImplementation()!;
    const order: string[] = [];
    let joinStarts = 0;
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input).endsWith("/join")) {
        const number = ++joinStarts;
        order.push(`join${number}`);
        if (number === 1) {
          await pendingJoin.promise;
          if (failFirstJoin)
            return json({ error: { message: "Old Join failed" } }, 500);
        }
      }
      if (String(input).endsWith("/leave")) {
        order.push("leave");
        if (failFirstJoin)
          return json({ error: { message: "No membership" } }, 403);
      }
      return normalFetch(input, init);
    });
    const first = await mount();
    await settle(() =>
      fireEvent.click(screen.getByRole("button", { name: "Leave" })),
    );
    const navigated = fake.push.mock.calls.length;
    first.unmount();
    await mount();
    const startsBeforeCompletion = joinStarts;
    const historyBeforeCompletion = history.mock.calls.length;
    await settle(() => pendingJoin.resolve());
    expect(navigated).toBe(1);
    expect(startsBeforeCompletion).toBe(1);
    expect(historyBeforeCompletion).toBe(0);
    expect(order).toEqual(["join1", "leave", "join2"]);
    expect(history).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Backend Otter")).toBeDefined();
    await advance(15_000);
    expect(heartbeats()).toHaveLength(1);
  },
);

test("a pending Leave in one room does not hold up a different room's Join", async () => {
  const pendingLeave = deferred<void>();
  const normalFetch = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (input, init) => {
    if (String(input).endsWith("/leave")) await pendingLeave.promise;
    return normalFetch(input, init);
  });
  const first = await mount();
  await settle(() =>
    fireEvent.click(screen.getByRole("button", { name: "Leave" })),
  );
  first.unmount();
  await settle(() => {
    render(<ChatRoom room={otherRoom} />);
  });
  const otherStarted = joins().some(([input]) =>
    String(input).includes(`/rooms/${otherRoom.id}/join`),
  );
  await settle(() => pendingLeave.resolve());
  expect(otherStarted).toBe(true);
  expect(screen.getByRole("heading", { name: "Marston" })).toBeDefined();
  expect(screen.getByText("Backend Otter")).toBeDefined();
});

test("recovers missed messages once in order, preserving history ownership after live duplicates", async () => {
  await mount();
  const pending = deferred<ChatMessage[]>();
  history.mockReturnValueOnce(pending.promise);
  await settle(() => emit("CHANNEL_ERROR"));
  expect(screen.getByTestId("connection-banner").textContent).toMatch(/lost/);
  await settle(() => {
    emit("SUBSCRIBED");
    emit("SUBSCRIBED");
    live(message("m4", 4));
    live(message("m2", 2));
  });
  expect(history).toHaveBeenLastCalledWith(room.id, "m1");
  expect(history).toHaveBeenCalledTimes(2);
  const catchUp = fetchMock.mock.calls.find(([url]) =>
    String(url).includes("?after=m1"),
  );
  expect(new Headers(catchUp?.[1]?.headers).get("Authorization")).toBe(
    "Bearer persisted-token",
  );
  await settle(() =>
    pending.resolve([message("m2", 2, true), message("m3", 3, false)]),
  );
  await settle(() => live(message("m2", 2)));
  expect(bodies()).toEqual(["m1", "m2", "m3", "m4"]);
  expect(
    screen.getByText("m2", { selector: "p" }).closest("article")?.dataset
      .ownMessage,
  ).toBe("true");
  expect(screen.getByTestId("connection-banner").textContent).toBe(
    "Reconnected",
  );
});

test("freezes the cursor before batched reconnect/live callbacks, rather than after React renders", async () => {
  await mount();
  history.mockResolvedValueOnce([message("m2", 2, false)]);
  await settle(() => {
    emit("CHANNEL_ERROR");
    live(message("m4", 4));
    emit("SUBSCRIBED");
    live(message("m3", 3));
  });
  expect(history).toHaveBeenLastCalledWith(room.id, "m1");
  expect(bodies()).toEqual(["m1", "m2", "m3", "m4"]);
});

test("initial/duplicate SUBSCRIBED and participant-count changes do not fetch catch-up or rejoin", async () => {
  const view = await mount((child) => child, false);
  await settle(() => {
    emit("TIMED_OUT");
    emit("SUBSCRIBED");
    emit("SUBSCRIBED");
  });
  view.rerender(<ChatRoom room={{ ...room, participant_count: 12 }} />);
  await settle();
  expect(history).toHaveBeenCalledExactlyOnceWith(room.id, undefined);
  expect(joins()).toHaveLength(1);
  expect(fake.channels).toHaveLength(1);
  expect(screen.getByText("12 people here")).toBeDefined();
});

test.each(["CHANNEL_ERROR", "TIMED_OUT", "CLOSED"])(
  "%s starts one catch-up only after resubscription",
  async (state) => {
    await mount();
    await settle(() => {
      emit(state);
      emit(state);
    });
    expect(history).toHaveBeenCalledTimes(1);
    await settle(() => {
      emit("SUBSCRIBED");
      emit("SUBSCRIBED");
    });
    expect(history).toHaveBeenCalledTimes(2);
    expect(history).toHaveBeenLastCalledWith(room.id, "m1");
  },
);

test("empty initial history falls back to the existing recent-history request", async () => {
  history.mockResolvedValueOnce([]);
  await mount();
  await settle(() => emit("CLOSED"));
  history.mockResolvedValueOnce([message("m2", 2)]);
  await settle(() => emit("SUBSCRIBED"));
  expect(history).toHaveBeenLastCalledWith(room.id, undefined);
  expect(bodies()).toEqual(["m2"]);
});

test("an empty catch-up verifies the gap, including live arrivals, without extra polling", async () => {
  await mount();
  const pending = deferred<ChatMessage[]>();
  history.mockReturnValueOnce(pending.promise);
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
    live(message("m3", 3));
  });
  await settle(() => pending.resolve([]));
  expect(history).toHaveBeenCalledTimes(2);
  await settle(() => {
    emit("CLOSED");
    emit("SUBSCRIBED");
  });
  expect(history).toHaveBeenLastCalledWith(room.id, "m3");
});

test("serializes repeated drops and keeps the first frozen cursor until the latest gap is verified", async () => {
  await mount();
  const first = deferred<ChatMessage[]>(),
    second = deferred<ChatMessage[]>();
  history
    .mockReturnValueOnce(first.promise)
    .mockReturnValueOnce(second.promise);
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
    live(message("m3", 3));
  });
  await settle(() => {
    emit("CLOSED");
    emit("SUBSCRIBED");
  });
  expect(history).toHaveBeenCalledTimes(2);
  await settle(() => first.resolve([message("m2", 2)]));
  expect(history).toHaveBeenCalledTimes(3);
  expect(history.mock.calls.slice(1)).toEqual([
    [room.id, "m1"],
    [room.id, "m1"],
  ]);
  await settle(() => second.resolve([message("m2", 2), message("m4", 4)]));
  expect(bodies()).toEqual(["m1", "m2", "m3", "m4"]);
});

test("bounds retries, retains an unverified cursor, and allows explicit recovery after failures", async () => {
  await mount();
  history
    .mockRejectedValueOnce(new Error("offline"))
    .mockRejectedValueOnce(new Error("offline"))
    .mockRejectedValueOnce(new Error("offline"));
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
    live(message("m4", 4));
  });
  await advance(1_000);
  await advance(3_000);
  expect(history).toHaveBeenCalledTimes(4);
  await advance(60_000);
  expect(history).toHaveBeenCalledTimes(4);
  expect(screen.getByRole("alert").textContent).toMatch(/could not be loaded/);
  history.mockResolvedValueOnce([message("m2", 2), message("m3", 3)]);
  await settle(() =>
    fireEvent.click(screen.getByRole("button", { name: "Retry messages" })),
  );
  expect(history.mock.calls.slice(1).every(([, after]) => after === "m1")).toBe(
    true,
  );
  expect(bodies()).toEqual(["m1", "m2", "m3", "m4"]);
  expect(screen.queryByRole("alert")).toBeNull();
});

test("a later real reconnect recovers a failed fetch using the original cursor", async () => {
  await mount();
  history.mockRejectedValueOnce(new Error("offline"));
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
    live(message("m4", 4));
  });
  history.mockResolvedValueOnce([message("m2", 2)]);
  await settle(() => {
    emit("CLOSED");
    emit("SUBSCRIBED");
  });
  await advance(4_000);
  expect(history.mock.calls.slice(1)).toEqual([
    [room.id, "m1"],
    [room.id, "m1"],
  ]);
  expect(bodies()).toEqual(["m1", "m2", "m4"]);
});

test("an initial history response cannot verify a gap opened while that request was pending", async () => {
  const initial = deferred<ChatMessage[]>();
  history
    .mockReturnValueOnce(initial.promise)
    .mockResolvedValueOnce([message("missed", 2)]);
  await mount();
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
    live(message("live", 3));
  });
  expect(history).toHaveBeenCalledTimes(1);
  await settle(() => initial.resolve([message("old", 1)]));
  expect(history.mock.calls).toEqual([
    [room.id, undefined],
    [room.id, undefined],
  ]);
  expect(bodies()).toEqual(["old", "missed", "live"]);
});

test("overlapping send/history/live responses keep one owned message and do not move the gap cursor", async () => {
  await mount();
  const post = deferred<ChatMessage[]>(),
    catchUp = deferred<ChatMessage[]>();
  send.mockImplementationOnce(async () => (await post.promise)[0]);
  const input = screen.getByLabelText("Message Library West");
  fireEvent.change(input, { target: { value: "own" } });
  await settle(() => fireEvent.keyDown(input, { key: "Enter" }));
  history.mockReturnValueOnce(catchUp.promise);
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
    live(message("own", 4));
  });
  await settle(() => post.resolve([message("own", 4)]));
  await settle(() =>
    catchUp.resolve([message("m2", 2), message("own", 4, true)]),
  );
  expect(history).toHaveBeenLastCalledWith(room.id, "m1");
  expect(bodies()).toEqual(["m1", "m2", "own"]);
  expect(
    screen.getByText("own", { selector: "p" }).closest("article")?.dataset
      .ownMessage,
  ).toBe("true");
});

test("accepts one newest-20 server response without paging into older history", async () => {
  await mount();
  const newest = Array.from({ length: 20 }, (_, i) =>
    message(`recent-${i}`, i + 10),
  );
  history.mockResolvedValueOnce(newest);
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
  });
  expect(history).toHaveBeenCalledTimes(2);
  expect(bodies()).toEqual(["m1", ...newest.map((item) => item.body)]);
});

test("Leave immediately stops recovery, live events and heartbeats; late history cannot restore them", async () => {
  await mount();
  const pending = deferred<ChatMessage[]>();
  history.mockReturnValueOnce(pending.promise);
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
  });
  const old = currentChannel();
  await settle(() =>
    fireEvent.click(screen.getByRole("button", { name: "Leave" })),
  );
  expect(fake.push).toHaveBeenCalledExactlyOnceWith("/");
  expect(leaves()).toHaveLength(1);
  expect(old.removed).toBe(true);
  await settle(() => {
    pending.resolve([message("stale", 2)]);
    live(message("late-live", 3), old);
    emit("SUBSCRIBED", old);
  });
  await advance(30_000);
  expect(screen.queryByText("stale")).toBeNull();
  expect(screen.queryByText("late-live")).toBeNull();
  expect(heartbeats()).toHaveLength(0);
  expect(history).toHaveBeenCalledTimes(2);
  expect(fake.client.auth.signOut).not.toHaveBeenCalled();
});

test("room changes ignore old history, sends and channel callbacks", async () => {
  const view = await mount();
  const pending = deferred<ChatMessage[]>(),
    post = deferred<ChatMessage[]>();
  history.mockReturnValueOnce(pending.promise).mockResolvedValueOnce([]);
  send.mockImplementationOnce(async () => (await post.promise)[0]);
  fireEvent.change(screen.getByLabelText("Message Library West"), {
    target: { value: "old-send" },
  });
  await settle(() =>
    fireEvent.keyDown(screen.getByLabelText("Message Library West"), {
      key: "Enter",
    }),
  );
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
  });
  const old = currentChannel();
  await settle(() => view.rerender(<ChatRoom room={otherRoom} />));
  await settle(() => {
    pending.resolve([message("stale-history", 2)]);
    post.resolve([message("old-send", 3)]);
    live(message("stale-live", 4), old);
    emit("SUBSCRIBED", old);
  });
  expect(bodies()).toEqual([]);
  expect(history).toHaveBeenCalledTimes(3);
  expect(currentChannel().topic).toBe(`room:${otherRoom.id}`);
  expect(leaves()).toHaveLength(0);
});

test("cleanup clears retries and heartbeat without sending Leave or signing out", async () => {
  const view = await mount();
  history.mockRejectedValueOnce(new Error("offline"));
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
  });
  view.unmount();
  await advance(60_000);
  expect(history).toHaveBeenCalledTimes(2);
  expect(heartbeats()).toHaveLength(0);
  expect(leaves()).toHaveLength(0);
  expect(fake.client.auth.signOut).not.toHaveBeenCalled();
  expect(fake.channels.every((channel) => channel.removed)).toBe(true);
});

test("a 20-second drop retains the backend nickname/session and resumes exactly one heartbeat", async () => {
  await mount();
  await advance(15_000);
  await settle(() => {
    offline = true;
    emit("CHANNEL_ERROR");
  });
  await advance(20_000);
  await settle(() => {
    offline = false;
    emit("SUBSCRIBED");
    emit("SUBSCRIBED");
  });
  await advance(10_000);
  expect(heartbeats()).toHaveLength(3);
  expect(successfulHeartbeats).toBe(2);
  expect(joins()).toHaveLength(1);
  expect(screen.getByText("Backend Otter")).toBeDefined();
  expect(fake.client.auth.signInAnonymously).not.toHaveBeenCalled();
  expect(fake.client.auth.signOut).not.toHaveBeenCalled();
  for (const [, init] of heartbeats())
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      "Bearer persisted-token",
    );
});

test("failed initial history cannot promote a live arrival into a verified cursor", async () => {
  history.mockRejectedValueOnce(new Error("history unavailable"));
  await mount();
  await settle(() => live(message("m4", 4)));
  history.mockResolvedValueOnce([message("m1", 1), message("m2", 2)]);
  await advance(1_000);
  expect(history).toHaveBeenLastCalledWith(room.id, undefined);
  expect(bodies()).toEqual(["m1", "m2", "m4"]);
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
  });
  expect(history).toHaveBeenLastCalledWith(room.id, "m4");
});

test("a fresh room mount reuses the persisted session and backend nickname without an old timer", async () => {
  const first = await mount();
  first.unmount();
  await mount();
  await advance(15_000);
  expect(screen.getByText("Backend Otter")).toBeDefined();
  expect(heartbeats()).toHaveLength(1);
  expect(fake.channels.filter((channel) => !channel.removed)).toHaveLength(1);
  expect(fake.client.auth.signInAnonymously).not.toHaveBeenCalled();
  expect(fake.client.auth.signOut).not.toHaveBeenCalled();
  expect(leaves()).toHaveLength(0);
});

test("StrictMode owns one channel, one initial history fetch, one catch-up and one heartbeat", async () => {
  await mount((child) => <StrictMode>{child}</StrictMode>);
  expect(history).toHaveBeenCalledTimes(1);
  expect(fake.channels).toHaveLength(1);
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
    emit("SUBSCRIBED");
  });
  expect(history).toHaveBeenCalledTimes(2);
  await advance(30_000);
  expect(heartbeats()).toHaveLength(2);
  expect(leaves()).toHaveLength(0);
});

test("Activity return waits for channel removal, ignores stale catch-up and starts one new visit", async () => {
  const page = (mode: "visible" | "hidden") => (
    <Activity mode={mode}>
      <ChatRoom room={room} />
    </Activity>
  );
  const view = render(page("visible"));
  await settle();
  await settle(() => emit("SUBSCRIBED"));
  const pending = deferred<ChatMessage[]>(),
    removed = deferred<string>();
  history
    .mockReturnValueOnce(pending.promise)
    .mockResolvedValueOnce([message("current", 4)]);
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
  });
  fake.client.removeChannel.mockImplementationOnce(() => removed.promise);
  await settle(() => view.rerender(page("hidden")));
  await settle(() => view.rerender(page("visible")));
  expect(fake.channels).toHaveLength(1);
  await settle(() => removed.resolve("ok"));
  expect(fake.channels).toHaveLength(2);
  await settle(() => {
    pending.resolve([message("stale-hidden", 2)]);
    emit("SUBSCRIBED");
    emit("SUBSCRIBED");
  });
  expect(history).toHaveBeenCalledTimes(3);
  expect(screen.queryByText("stale-hidden")).toBeNull();
  expect(screen.getByText("current", { selector: "p" })).toBeDefined();
  await advance(15_000);
  expect(heartbeats()).toHaveLength(1);
  expect(leaves()).toHaveLength(0);
  expect(fake.client.auth.signInAnonymously).not.toHaveBeenCalled();
});

test("Activity retains sent-message ownership without treating recovered history as a new submission", async () => {
  const page = (mode: "visible" | "hidden") => (
    <Activity mode={mode}>
      <ChatRoom room={room} />
    </Activity>
  );
  const view = render(page("visible"));
  await settle();
  fireEvent.change(screen.getByLabelText("Message Library West"), {
    target: { value: "own" },
  });
  await settle(() =>
    fireEvent.keyDown(screen.getByLabelText("Message Library West"), {
      key: "Enter",
    }),
  );
  await advance(16);
  history.mockResolvedValueOnce([]);
  await settle(() => view.rerender(page("hidden")));
  await settle(() => view.rerender(page("visible")));
  await settle(() => emit("SUBSCRIBED"));
  expect(
    screen.getByText("own", { selector: "p" }).closest("article")?.dataset
      .ownMessage,
  ).toBe("true");
  const region = screen.getByTestId("message-scroll-region");
  const scrollTo = vi.fn();
  Object.defineProperties(region, {
    clientHeight: { configurable: true, value: 200 },
    scrollHeight: { configurable: true, value: 1000 },
    scrollTop: { configurable: true, value: 100 },
    scrollTo: { configurable: true, value: scrollTo },
  });
  fireEvent.scroll(region);
  history.mockResolvedValueOnce([message("other-tab", 5, true)]);
  await settle(() => {
    emit("CHANNEL_ERROR");
    emit("SUBSCRIBED");
  });
  await advance(16);
  expect(scrollTo).not.toHaveBeenCalled();
  expect(region.scrollTop).toBe(100);
  expect(screen.getByRole("button", { name: /1 new message/i })).toBeDefined();
  expect(
    screen.getByText("other-tab", { selector: "p" }).closest("article")?.dataset
      .ownMessage,
  ).toBe("true");
});
