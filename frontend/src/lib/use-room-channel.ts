"use client";

import { useEffect, useRef, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";

import type { ChatMessage } from "@/lib/placechat-types";
import { ensureSession } from "@/lib/session";
import { getSupabaseBrowserClient } from "@/lib/supabase";

/** Channel status for the connection banner (PBI-17, #21). */
export type RoomChannelStatus =
  "connecting" | "subscribed" | "error" | "closed";

const STATUS_BY_STATE: Record<string, RoomChannelStatus> = {
  SUBSCRIBED: "subscribed",
  CHANNEL_ERROR: "error",
  TIMED_OUT: "error",
  CLOSED: "closed",
};

/**
 * Receive `message.created` events for one room (Technical Design §6.5, §7.3).
 *
 * The channel is private, so Realtime checks the signed-in user's token; the
 * browser can only receive. After an error, supabase-js rejoins on its own
 * with backoff (this also covers the `MissingPartition` error seen in spike
 * #30), and the status goes back to "subscribed" when it succeeds.
 */
export function useRoomChannel(
  roomId: string,
  onMessage: (message: ChatMessage) => void,
): RoomChannelStatus {
  const [state, setState] = useState<{
    roomId: string;
    status: RoomChannelStatus;
  }>({ roomId, status: "connecting" });
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  });

  useEffect(() => {
    let cancelled = false;
    let channel: RealtimeChannel | undefined;
    const report = (status: RoomChannelStatus) => {
      if (!cancelled) setState({ roomId, status });
    };

    async function connect() {
      try {
        const supabase = getSupabaseBrowserClient();
        await ensureSession();
        // Load the user's token before joining; a private join without it is refused.
        await supabase.realtime.setAuth();
        if (cancelled) return;

        channel = supabase
          .channel(`room:${roomId}`, { config: { private: true } })
          .on("broadcast", { event: "message.created" }, ({ payload }) => {
            const message = payload as ChatMessage;
            // Only this room's messages, even if an event arrives on the wrong topic (#20).
            if (message?.room_id !== roomId) return;
            onMessageRef.current(message);
          })
          .subscribe((channelState) => {
            report(STATUS_BY_STATE[channelState] ?? "connecting");
          });
      } catch {
        report("error");
      }
    }

    void connect();

    return () => {
      cancelled = true;
      if (channel) void getSupabaseBrowserClient().removeChannel(channel);
    };
  }, [roomId]);

  // A new room starts as "connecting" until its own channel reports back.
  return state.roomId === roomId ? state.status : "connecting";
}
