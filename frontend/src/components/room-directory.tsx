"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listRooms } from "@/lib/placechat-api";
import type { RoomSummary } from "@/lib/placechat-types";

const categoryStyles: Record<RoomSummary["category"], string> = {
  academic: "bg-sky-50 text-sky-700 ring-sky-600/10",
  dining: "bg-orange-50 text-orange-700 ring-orange-600/10",
  library: "bg-violet-50 text-violet-700 ring-violet-600/10",
  recreation: "bg-emerald-50 text-emerald-700 ring-emerald-600/10",
  "student life": "bg-rose-50 text-rose-700 ring-rose-600/10",
};

function formatCategory(category: RoomSummary["category"]) {
  return category.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function RoomCard({ room }: { room: RoomSummary }) {
  const participantLabel = `${room.participant_count} ${
    room.participant_count === 1 ? "person" : "people"
  } here`;

  return (
    <Link
      href={`/rooms/${room.id}`}
      className="group relative flex min-h-56 flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white p-6 shadow-sm transition duration-200 hover:-translate-y-1 hover:border-violet-200 hover:shadow-xl hover:shadow-violet-100/70 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-violet-600"
      aria-label={`Join ${room.name}, ${participantLabel}`}
    >
      <div className="flex items-start justify-between gap-4">
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${categoryStyles[room.category]}`}
        >
          {formatCategory(room.category)}
        </span>
        <span className="grid h-9 w-9 place-items-center rounded-full bg-slate-50 text-slate-400 transition group-hover:bg-violet-600 group-hover:text-white">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="h-4 w-4"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m9 18 6-6-6-6"
            />
          </svg>
        </span>
      </div>

      <div className="mt-8 flex-1">
        <h2 className="text-xl font-bold tracking-[-0.025em] text-slate-950">
          {room.name}
        </h2>
        <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-600">
          {room.description}
        </p>
      </div>

      <div className="mt-6 flex items-center gap-2 border-t border-slate-100 pt-4 text-sm font-medium text-slate-500">
        <span className="relative flex h-2.5 w-2.5">
          {room.participant_count > 0 ? (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />
          ) : null}
          <span
            className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
              room.participant_count > 0 ? "bg-emerald-500" : "bg-slate-300"
            }`}
          />
        </span>
        {participantLabel}
      </div>
    </Link>
  );
}

function RoomSkeleton() {
  return (
    <div
      className="min-h-56 animate-pulse rounded-3xl border border-slate-200 bg-white p-6"
      aria-hidden="true"
    >
      <div className="h-6 w-24 rounded-full bg-slate-100" />
      <div className="mt-9 h-6 w-2/3 rounded bg-slate-100" />
      <div className="mt-3 h-4 w-full rounded bg-slate-100" />
      <div className="mt-2 h-4 w-4/5 rounded bg-slate-100" />
      <div className="mt-7 h-px bg-slate-100" />
      <div className="mt-4 h-4 w-28 rounded bg-slate-100" />
    </div>
  );
}

export function RoomDirectory() {
  const [rooms, setRooms] = useState<RoomSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleRetry = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const nextRooms = await listRooms();
      setRooms([...nextRooms].sort((a, b) => a.name.localeCompare(b.name)));
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "We couldn’t load campus rooms. Please try again.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    listRooms().then(
      (nextRooms) => {
        if (cancelled) return;
        setRooms([...nextRooms].sort((a, b) => a.name.localeCompare(b.name)));
        setIsLoading(false);
      },
      (caught: unknown) => {
        if (cancelled) return;
        setError(
          caught instanceof Error
            ? caught.message
            : "We couldn’t load campus rooms. Please try again.",
        );
        setIsLoading(false);
      },
    );

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section
      className="mx-auto w-full max-w-6xl px-5 sm:px-8"
      aria-labelledby="rooms-heading"
      aria-busy={isLoading}
    >
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-violet-600">Open now</p>
          <h2
            id="rooms-heading"
            className="mt-1 text-2xl font-bold tracking-[-0.035em] text-slate-950 sm:text-3xl"
          >
            Campus rooms
          </h2>
        </div>
        {!isLoading && !error ? (
          <p className="hidden text-sm text-slate-500 sm:block">
            {rooms.length} places to join
          </p>
        ) : null}
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded-3xl border border-rose-200 bg-rose-50 p-6 text-rose-950"
        >
          <p className="font-semibold">
            Rooms are taking a little longer to arrive.
          </p>
          <p className="mt-1 text-sm text-rose-800">{error}</p>
          <button
            type="button"
            onClick={() => {
              void handleRetry();
            }}
            className="mt-4 min-h-11 rounded-xl bg-rose-700 px-4 text-sm font-semibold text-white transition hover:bg-rose-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-700"
          >
            Try again
          </button>
        </div>
      ) : null}

      {isLoading ? (
        <div
          className="grid gap-4 md:grid-cols-2 lg:grid-cols-3"
          aria-label="Loading rooms"
        >
          {Array.from({ length: 6 }, (_, index) => (
            <RoomSkeleton key={index} />
          ))}
        </div>
      ) : null}

      {!isLoading && !error && rooms.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-300 bg-white/70 p-10 text-center">
          <h3 className="font-semibold text-slate-900">
            No rooms are open right now
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            Check back soon for a conversation.
          </p>
        </div>
      ) : null}

      {!isLoading && !error && rooms.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {rooms.map((room) => (
            <RoomCard key={room.id} room={room} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
