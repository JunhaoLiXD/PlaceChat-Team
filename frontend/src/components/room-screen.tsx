"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { ChatRoom } from "@/components/chat-room";
import { listRooms } from "@/lib/placechat-api";
import type { RoomSummary } from "@/lib/placechat-types";

type RoomState =
  | { status: "loading" }
  | { status: "ready"; room: RoomSummary }
  | { status: "missing" }
  | { status: "failed"; message: string };

function CenteredCard({ children }: { children: React.ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center px-5">
      <div className="max-w-sm text-center">{children}</div>
    </main>
  );
}

/** Loads the room from the active-rooms list, so real room ids from the API work (#17). */
export function RoomScreen({ roomId }: { roomId: string }) {
  const [state, setState] = useState<RoomState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    listRooms().then(
      (rooms) => {
        if (cancelled) return;
        const room = rooms.find((candidate) => candidate.id === roomId);
        setState(room ? { status: "ready", room } : { status: "missing" });
      },
      (caught: unknown) => {
        if (cancelled) return;
        setState({
          status: "failed",
          message:
            caught instanceof Error
              ? caught.message
              : "We couldn’t load this room. Please try again.",
        });
      },
    );

    return () => {
      cancelled = true;
    };
  }, [roomId]);

  if (state.status === "ready") {
    return <ChatRoom room={state.room} />;
  }

  if (state.status === "loading") {
    return (
      <CenteredCard>
        <div className="flex items-center justify-center gap-3 text-sm font-medium text-slate-500">
          <span
            className="h-5 w-5 animate-spin rounded-full border-2 border-violet-200 border-t-violet-600"
            aria-hidden="true"
          />
          Joining room…
        </div>
      </CenteredCard>
    );
  }

  return (
    <CenteredCard>
      <h1 className="text-lg font-bold text-slate-950">
        {state.status === "missing" ? "Room not found" : "Something went wrong"}
      </h1>
      <p role="alert" className="mt-2 text-sm text-slate-600">
        {state.status === "missing"
          ? "This room does not exist or has been closed."
          : state.message}
      </p>
      <Link
        href="/"
        className="mt-5 inline-flex min-h-10 items-center rounded-xl bg-violet-600 px-4 text-sm font-semibold text-white hover:bg-violet-700"
      >
        Back to all rooms
      </Link>
    </CenteredCard>
  );
}
