"use client";

import { useEffect, useState } from "react";

import type { RoomChannelStatus } from "@/lib/use-room-channel";

export type ConnectionBanner = "lost" | "restored" | null;

/** How long "Reconnected" stays on screen. */
export const RESTORED_BANNER_MS = 3_000;

/**
 * Turn channel status changes into the C2 banner (Technical Design §2.2):
 * "Connection lost, reconnecting…" after a working connection drops, then
 * "Reconnected" for a moment once it is back. The first connect shows nothing.
 */
export function useConnectionBanner(
  status: RoomChannelStatus,
): ConnectionBanner {
  const [previous, setPrevious] = useState(status);
  const [wasConnected, setWasConnected] = useState(status === "subscribed");
  const [banner, setBanner] = useState<ConnectionBanner>(null);

  // React's pattern for state that follows a changing prop: update during render.
  if (status !== previous) {
    setPrevious(status);
    if (status === "subscribed") {
      setWasConnected(true);
      if (banner === "lost") setBanner("restored");
    } else if (status !== "connecting" && wasConnected) {
      setBanner("lost");
    }
  }

  useEffect(() => {
    if (banner !== "restored") return;
    const timer = window.setTimeout(() => setBanner(null), RESTORED_BANNER_MS);
    return () => window.clearTimeout(timer);
  }, [banner]);

  return banner;
}
