"use client";

import { useEffect, useRef } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";

import { ensureSession } from "@/lib/session";
import { getSupabaseBrowserClient } from "@/lib/supabase";

export interface RoomCountEvent {
  room_id: string;
  count: number;
}

function isRoomCountEvent(payload: unknown): payload is RoomCountEvent {
  if (!payload || typeof payload !== "object") return false;
  const candidate = payload as Partial<RoomCountEvent>;
  return (
    typeof candidate.room_id === "string" &&
    Number.isInteger(candidate.count) &&
    (candidate.count ?? -1) >= 0
  );
}

/** Receive live participant counts for every room (PBI-28, contract from PBI-29). */
export function useRoomCountsChannel(
  enabled: boolean,
  onCount: (event: RoomCountEvent) => void,
) {
  const onCountRef = useRef(onCount);

  useEffect(() => {
    onCountRef.current = onCount;
  });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let channel: RealtimeChannel | undefined;

    async function connect() {
      try {
        const supabase = getSupabaseBrowserClient();
        await ensureSession();
        await supabase.realtime.setAuth();
        if (cancelled) return;

        channel = supabase
          .channel("rooms", { config: { private: true } })
          .on("broadcast", { event: "room.count" }, ({ payload }) => {
            if (isRoomCountEvent(payload)) onCountRef.current(payload);
          })
          .subscribe();
      } catch {
        // The REST count remains usable when Realtime is temporarily unavailable.
      }
    }

    void connect();

    return () => {
      cancelled = true;
      if (channel) void getSupabaseBrowserClient().removeChannel(channel);
    };
  }, [enabled]);
}
