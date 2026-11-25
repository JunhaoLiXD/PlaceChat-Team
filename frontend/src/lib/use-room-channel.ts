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
 * Removal is the third callback; the fourth reports status synchronously so
 * recovery can freeze its cursor before live arrivals in the same React batch.
 * The fifth callback receives validated participant-count broadcasts.
 *
 * Pass `null` to stay disconnected (mock data mode has no Supabase project).
 */
export function useRoomChannel(
  roomId: string | null,
  onMessage: (message: ChatMessage) => void,
  onMessageRemoved?: (messageId: string) => void,
  onStatus?: (status: RoomChannelStatus) => void,
  onParticipantCount?: (count: number) => void,
): RoomChannelStatus {
  const [state, setState] = useState<{
    roomId: string | null;
    status: RoomChannelStatus;
  }>({ roomId, status: "connecting" });
  const onMessageRef = useRef(onMessage);
  const onStatusRef = useRef(onStatus);
  const removalRef = useRef<Promise<unknown> | undefined>(undefined);
  const onMessageRemovedRef = useRef(onMessageRemoved);
  const onParticipantCountRef = useRef(onParticipantCount);

  useEffect(() => {
    onMessageRef.current = onMessage;
    onStatusRef.current = onStatus;
  });
  useEffect(() => {
    onMessageRemovedRef.current = onMessageRemoved;
    onParticipantCountRef.current = onParticipantCount;
  });

  useEffect(() => {
    if (roomId === null) return;
    let cancelled = false;
    let channel: RealtimeChannel | undefined;
    const report = (status: RoomChannelStatus) => {
      if (cancelled) return;
      // Notify synchronously: live messages can follow SUBSCRIBED in the same
      // React batch, before an effect watching the rendered status could run.
      onStatusRef.current?.(status);
      setState({ roomId, status });
    };

    async function connect() {
      try {
        await removalRef.current;
        if (cancelled) return;
        const supabase = getSupabaseBrowserClient();
        await ensureSession();
        if (cancelled) return;
        // Load the user's token before joining; a private join without it is refused.
        await supabase.realtime.setAuth();
        if (cancelled) return;

        channel = supabase
          .channel(`room:${roomId}`, { config: { private: true } })
          .on("broadcast", { event: "message.created" }, ({ payload }) => {
            const message = payload as ChatMessage;
            // Only this room's messages, even if an event arrives on the wrong topic (#20).
            if (cancelled || message?.room_id !== roomId) return;
            onMessageRef.current(message);
          })
          .on("broadcast", { event: "message.removed" }, ({ payload }) => {
            const messageId = (payload as { id?: unknown })?.id;
            if (cancelled || typeof messageId !== "string") return;
            onMessageRemovedRef.current?.(messageId);
          })
          .on("broadcast", { event: "presence.updated" }, ({ payload }) => {
            const count = (payload as { count?: unknown } | null)?.count;
            if (
              !cancelled &&
              Number.isInteger(count) &&
              (count as number) >= 0
            ) {
              onParticipantCountRef.current?.(count as number);
            }
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
      if (channel) {
        removalRef.current = getSupabaseBrowserClient()
          .removeChannel(channel)
          .catch(() => {
            // Local callbacks are already disabled, even if unsubscribe fails.
          });
      }
    };
  }, [roomId]);

  if (roomId === null) return "closed";
  // A new room starts as "connecting" until its own channel reports back.
  return state.roomId === roomId ? state.status : "connecting";
}
