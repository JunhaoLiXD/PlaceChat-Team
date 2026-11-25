import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { useRoomCountsChannel } from "@/lib/use-room-counts-channel";

type BroadcastHandler = (event: { payload: unknown }) => void;

const fake = vi.hoisted(() => {
  const record = {
    topic: "",
    options: undefined as unknown,
    broadcast: undefined as BroadcastHandler | undefined,
  };
  const client = {
    realtime: { setAuth: vi.fn() },
    channel: vi.fn(),
    removeChannel: vi.fn(),
  };
  return { record, client, ensureSession: vi.fn() };
});

vi.mock("@/lib/supabase", () => ({
  getSupabaseBrowserClient: () => fake.client,
}));

vi.mock("@/lib/session", () => ({
  ensureSession: fake.ensureSession,
}));

beforeEach(() => {
  vi.resetAllMocks();
  fake.record.topic = "";
  fake.record.options = undefined;
  fake.record.broadcast = undefined;
  fake.ensureSession.mockResolvedValue({});
  fake.client.realtime.setAuth.mockResolvedValue(undefined);
  fake.client.removeChannel.mockResolvedValue("ok");
  fake.client.channel.mockImplementation((topic: string, options: unknown) => {
    fake.record.topic = topic;
    fake.record.options = options;
    const channel = {
      on: (
        _type: string,
        _filter: { event: string },
        handler: BroadcastHandler,
      ) => {
        fake.record.broadcast = handler;
        return channel;
      },
      subscribe: () => channel,
    };
    return channel;
  });
});

test("subscribes to private room-count broadcasts and validates payloads", async () => {
  const onCount = vi.fn();
  const hook = renderHook(() => useRoomCountsChannel(true, onCount));

  await waitFor(() => expect(fake.client.channel).toHaveBeenCalledOnce());
  expect(fake.record.topic).toBe("rooms");
  expect(fake.record.options).toEqual({ config: { private: true } });

  act(() =>
    fake.record.broadcast?.({ payload: { room_id: "room-1", count: 4 } }),
  );
  act(() =>
    fake.record.broadcast?.({ payload: { room_id: "room-1", count: -2 } }),
  );
  act(() => fake.record.broadcast?.({ payload: { count: 2 } }));

  expect(onCount).toHaveBeenCalledExactlyOnceWith({
    room_id: "room-1",
    count: 4,
  });

  hook.unmount();
  expect(fake.client.removeChannel).toHaveBeenCalledOnce();
});

test("does not create a session in mock mode", async () => {
  renderHook(() => useRoomCountsChannel(false, vi.fn()));

  await Promise.resolve();
  expect(fake.ensureSession).not.toHaveBeenCalled();
  expect(fake.client.channel).not.toHaveBeenCalled();
});
