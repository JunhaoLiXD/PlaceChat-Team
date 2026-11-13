import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import type { ChatMessage } from "@/lib/placechat-types";
import { useRoomChannel } from "@/lib/use-room-channel";

type BroadcastHandler = (event: { payload: unknown }) => void;
type StatusHandler = (state: string) => void;

const fake = vi.hoisted(() => {
  const channels: {
    topic: string;
    options: unknown;
    broadcast?: BroadcastHandler;
    removed?: BroadcastHandler;
    status?: StatusHandler;
  }[] = [];
  const client = {
    realtime: { setAuth: vi.fn() },
    channel: vi.fn(),
    removeChannel: vi.fn(),
  };
  return { channels, client, ensureSession: vi.fn() };
});

vi.mock("@/lib/supabase", () => ({
  getSupabaseBrowserClient: () => fake.client,
}));

vi.mock("@/lib/session", () => ({
  ensureSession: fake.ensureSession,
}));

function message(roomId: string): ChatMessage {
  return {
    id: "m1",
    room_id: roomId,
    nickname: "Quiet Otter",
    body: "hello",
    created_at: "2026-10-21T12:00:00Z",
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  fake.channels.length = 0;
  fake.ensureSession.mockResolvedValue({});
  fake.client.realtime.setAuth.mockResolvedValue(undefined);
  fake.client.removeChannel.mockResolvedValue("ok");
  fake.client.channel.mockImplementation((topic: string, options: unknown) => {
    const record: (typeof fake.channels)[number] = { topic, options };
    fake.channels.push(record);
    const channel = {
      on: (_type: string, _filter: unknown, handler: BroadcastHandler) => {
        if (
          _filter &&
          (_filter as { event?: string }).event === "message.removed"
        ) {
          record.removed = handler;
        } else {
          record.broadcast = handler;
        }
        return channel;
      },
      subscribe: (handler: StatusHandler) => {
        record.status = handler;
        return channel;
      },
    };
    return channel;
  });
});

async function connected(
  roomId = "room-1",
  onMessage = vi.fn(),
  onMessageRemoved = vi.fn(),
) {
  const hook = renderHook(
    ({ id }) => useRoomChannel(id, onMessage, onMessageRemoved),
    {
      initialProps: { id: roomId },
    },
  );
  await waitFor(() => expect(fake.channels).toHaveLength(1));
  return { hook, onMessage, channel: fake.channels[0] };
}

describe("useRoomChannel", () => {
  test("joins the room's private channel after loading the session token", async () => {
    const { channel } = await connected();

    expect(channel.topic).toBe("room:room-1");
    expect(channel.options).toEqual({ config: { private: true } });
    expect(fake.ensureSession).toHaveBeenCalledOnce();
    expect(fake.client.realtime.setAuth).toHaveBeenCalledOnce();
  });

  test("reports the channel status for the connection banner", async () => {
    const { hook, channel } = await connected();
    expect(hook.result.current).toBe("connecting");

    act(() => channel.status?.("SUBSCRIBED"));
    expect(hook.result.current).toBe("subscribed");

    act(() => channel.status?.("CHANNEL_ERROR"));
    expect(hook.result.current).toBe("error");

    // supabase-js rejoins by itself after an error.
    act(() => channel.status?.("SUBSCRIBED"));
    expect(hook.result.current).toBe("subscribed");
  });

  test("passes on this room's messages and ignores other rooms", async () => {
    const { onMessage, channel } = await connected();

    act(() => channel.broadcast?.({ payload: message("room-1") }));
    act(() => channel.broadcast?.({ payload: message("room-2") }));

    expect(onMessage).toHaveBeenCalledExactlyOnceWith(message("room-1"));
  });

  test("passes removed message ids to the removal callback", async () => {
    const onMessageRemoved = vi.fn();
    const { channel } = await connected("room-1", vi.fn(), onMessageRemoved);

    act(() => channel.removed?.({ payload: { id: "m1" } }));
    act(() => channel.removed?.({ payload: { id: 42 } }));

    expect(onMessageRemoved).toHaveBeenCalledExactlyOnceWith("m1");
  });

  test("leaves the old channel when the room changes or the page closes", async () => {
    const { hook, channel } = await connected();

    hook.rerender({ id: "room-2" });
    expect(hook.result.current).toBe("connecting");
    expect(fake.client.removeChannel).toHaveBeenCalledOnce();
    await waitFor(() => expect(fake.channels).toHaveLength(2));
    expect(fake.channels[1].topic).toBe("room:room-2");

    // Late events from the old channel no longer change the new room's status.
    act(() => channel.status?.("SUBSCRIBED"));
    expect(hook.result.current).toBe("connecting");

    hook.unmount();
    expect(fake.client.removeChannel).toHaveBeenCalledTimes(2);
  });

  test("reports an error when the session cannot be created", async () => {
    fake.ensureSession.mockRejectedValue(new Error("offline"));

    const { result } = renderHook(() => useRoomChannel("room-1", vi.fn()));

    await waitFor(() => expect(result.current).toBe("error"));
    expect(fake.client.channel).not.toHaveBeenCalled();
  });

  test("stays disconnected when given no room (mock data mode)", async () => {
    const { result } = renderHook(() => useRoomChannel(null, vi.fn()));

    expect(result.current).toBe("closed");
    await Promise.resolve();
    expect(fake.ensureSession).not.toHaveBeenCalled();
    expect(fake.client.channel).not.toHaveBeenCalled();
  });
});
