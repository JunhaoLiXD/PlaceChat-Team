"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import {
  ApiRequestError,
  archiveAdminRoom,
  createAdminRoom,
  listAdminRooms,
  updateAdminRoom,
} from "@/lib/placechat-api";
import type {
  AdminRoom,
  AdminRoomCreate,
  RoomCategory,
} from "@/lib/placechat-types";

const CATEGORIES: RoomCategory[] = [
  "academic",
  "dining",
  "library",
  "recreation",
  "student life",
];

type LoadState = "loading" | "ready" | "failed" | "unauthorized";

interface RoomDraft {
  name: string;
  description: string;
  category: RoomCategory;
  latitude: string;
  longitude: string;
}

const EMPTY_DRAFT: RoomDraft = {
  name: "",
  description: "",
  category: "academic",
  latitude: "",
  longitude: "",
};

function sortRooms(rooms: AdminRoom[]): AdminRoom[] {
  return [...rooms].sort((left, right) => {
    if (left.status !== right.status) return left.status === "active" ? -1 : 1;
    return left.name.localeCompare(right.name);
  });
}

function formatCategory(category: RoomCategory) {
  return category.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isUnauthorized(error: unknown) {
  return (
    error instanceof ApiRequestError &&
    (error.status === 401 || error.status === 403)
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}

export function AdminRoomManager() {
  const [rooms, setRooms] = useState<AdminRoom[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState<RoomDraft>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [archiveCandidate, setArchiveCandidate] = useState<AdminRoom | null>(
    null,
  );
  const [isArchiving, setIsArchiving] = useState(false);

  const load = async () => {
    setLoadState("loading");
    setLoadError(null);
    try {
      setRooms(sortRooms(await listAdminRooms()));
      setLoadState("ready");
    } catch (caught) {
      if (isUnauthorized(caught)) {
        setLoadState("unauthorized");
      } else {
        setLoadError(errorMessage(caught));
        setLoadState("failed");
      }
    }
  };

  useEffect(() => {
    let cancelled = false;

    listAdminRooms().then(
      (nextRooms) => {
        if (cancelled) return;
        setRooms(sortRooms(nextRooms));
        setLoadState("ready");
      },
      (caught: unknown) => {
        if (cancelled) return;
        if (isUnauthorized(caught)) {
          setLoadState("unauthorized");
        } else {
          setLoadError(errorMessage(caught));
          setLoadState("failed");
        }
      },
    );

    return () => {
      cancelled = true;
    };
  }, []);

  const resetForm = () => {
    setDraft(EMPTY_DRAFT);
    setEditingId(null);
    setFormError(null);
  };

  const startEditing = (room: AdminRoom) => {
    setEditingId(room.id);
    setDraft({
      name: room.name,
      description: room.description,
      category: room.category,
      latitude: String(room.latitude),
      longitude: String(room.longitude),
    });
    setFormError(null);
    setSuccess(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    setSuccess(null);

    const latitude = Number(draft.latitude);
    const longitude = Number(draft.longitude);
    if (
      !draft.latitude.trim() ||
      !draft.longitude.trim() ||
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) ||
      latitude < -90 ||
      latitude > 90 ||
      longitude < -180 ||
      longitude > 180
    ) {
      setFormError(
        "Enter a valid latitude (-90 to 90) and longitude (-180 to 180).",
      );
      return;
    }

    const payload: AdminRoomCreate = {
      name: draft.name.trim(),
      description: draft.description.trim(),
      category: draft.category,
      latitude,
      longitude,
    };

    setIsSaving(true);
    try {
      const saved = editingId
        ? await updateAdminRoom(editingId, payload)
        : await createAdminRoom(payload);
      setRooms((current) =>
        sortRooms([...current.filter((room) => room.id !== saved.id), saved]),
      );
      setSuccess(
        editingId ? `Updated ${saved.name}.` : `Created ${saved.name}.`,
      );
      resetForm();
    } catch (caught) {
      if (isUnauthorized(caught)) {
        setLoadState("unauthorized");
      } else {
        setFormError(errorMessage(caught));
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleArchive = async () => {
    if (!archiveCandidate) return;
    setIsArchiving(true);
    setFormError(null);
    setSuccess(null);

    try {
      const archived = await archiveAdminRoom(archiveCandidate.id);
      setRooms((current) =>
        sortRooms([
          ...current.filter((room) => room.id !== archived.id),
          archived,
        ]),
      );
      if (editingId === archived.id) resetForm();
      setSuccess(`Archived ${archived.name}.`);
      setArchiveCandidate(null);
    } catch (caught) {
      if (isUnauthorized(caught)) {
        setArchiveCandidate(null);
        setLoadState("unauthorized");
      } else {
        setFormError(errorMessage(caught));
        setArchiveCandidate(null);
      }
    } finally {
      setIsArchiving(false);
    }
  };

  if (loadState === "unauthorized") {
    return (
      <main className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-2xl place-items-center px-5 py-12 text-center sm:px-8">
        <section className="w-full rounded-3xl border border-amber-400/20 bg-amber-400/10 p-8">
          <span
            className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-amber-300 text-xl font-black text-slate-950"
            aria-hidden="true"
          >
            !
          </span>
          <h1 className="mt-5 text-2xl font-bold tracking-[-0.035em] text-white">
            Not authorized
          </h1>
          <p
            role="alert"
            className="mx-auto mt-3 max-w-md text-sm leading-6 text-amber-100"
          >
            This page is only available to provisioned PlaceChat administrators.
            Sign in with an administrator account to continue.
          </p>
          <Link
            href="/admin/login"
            className="mt-6 inline-flex min-h-11 items-center rounded-xl bg-amber-300 px-5 text-sm font-bold text-slate-950 transition hover:bg-amber-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300"
          >
            Return to admin sign in
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-7xl px-5 py-10 sm:px-8 sm:py-12">
      <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-violet-300">
            Campus operations
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-[-0.045em] text-white sm:text-4xl">
            Room management
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
            Create and maintain the campus places available to the PlaceChat
            community. Archived rooms stay visible here for reference.
          </p>
        </div>
        <button
          type="button"
          onClick={resetForm}
          className="min-h-11 rounded-xl bg-violet-500 px-5 text-sm font-bold text-white transition hover:bg-violet-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-300"
        >
          Add room
        </button>
      </div>

      {success ? (
        <div
          role="status"
          className="mb-6 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-100"
        >
          {success}
        </div>
      ) : null}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(22rem,0.75fr)]">
        <section aria-labelledby="room-list-heading">
          <div className="mb-4 flex items-center justify-between gap-4">
            <h2 id="room-list-heading" className="text-lg font-bold text-white">
              All rooms
            </h2>
            {loadState === "ready" ? (
              <span className="text-sm text-slate-400">
                {rooms.length} {rooms.length === 1 ? "room" : "rooms"}
              </span>
            ) : null}
          </div>

          {loadState === "loading" ? (
            <div className="space-y-3" aria-label="Loading admin rooms">
              {Array.from({ length: 3 }, (_, index) => (
                <div
                  key={index}
                  className="h-36 animate-pulse rounded-2xl border border-white/10 bg-white/[0.05]"
                />
              ))}
            </div>
          ) : null}

          {loadState === "failed" ? (
            <div
              role="alert"
              className="rounded-2xl border border-rose-400/20 bg-rose-400/10 p-5 text-rose-100"
            >
              <p className="font-semibold">Rooms could not be loaded.</p>
              <p className="mt-1 text-sm">{loadError}</p>
              <button
                type="button"
                onClick={() => void load()}
                className="mt-4 min-h-10 rounded-lg bg-rose-200 px-4 text-sm font-bold text-rose-950"
              >
                Try again
              </button>
            </div>
          ) : null}

          {loadState === "ready" && rooms.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.04] p-8 text-center">
              <p className="font-semibold text-white">No rooms yet</p>
              <p className="mt-1 text-sm text-slate-400">
                Use the form to create the first campus room.
              </p>
            </div>
          ) : null}

          {loadState === "ready" && rooms.length > 0 ? (
            <div className="space-y-3">
              {rooms.map((room) => (
                <article
                  key={room.id}
                  className={`rounded-2xl border p-5 transition ${
                    editingId === room.id
                      ? "border-violet-400 bg-violet-400/10"
                      : "border-white/10 bg-white/[0.05]"
                  }`}
                >
                  <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-lg font-bold tracking-[-0.02em] text-white">
                          {room.name}
                        </h3>
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                            room.status === "active"
                              ? "bg-emerald-400/15 text-emerald-200"
                              : "bg-slate-700 text-slate-300"
                          }`}
                        >
                          {room.status === "active" ? "Active" : "Archived"}
                        </span>
                        <span className="rounded-full bg-white/[0.07] px-2.5 py-1 text-xs font-medium text-slate-300">
                          {formatCategory(room.category)}
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-300">
                        {room.description}
                      </p>
                      <p className="mt-3 font-mono text-xs text-slate-500">
                        {room.latitude}, {room.longitude}
                      </p>
                    </div>

                    {room.status === "active" ? (
                      <div className="flex shrink-0 gap-2">
                        <button
                          type="button"
                          onClick={() => startEditing(room)}
                          className="min-h-10 rounded-lg border border-white/15 px-3 text-sm font-semibold text-white transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-violet-400"
                          aria-label={`Edit ${room.name}`}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => setArchiveCandidate(room)}
                          className="min-h-10 rounded-lg border border-rose-400/25 px-3 text-sm font-semibold text-rose-200 transition hover:bg-rose-400/10 focus-visible:outline-2 focus-visible:outline-rose-300"
                          aria-label={`Archive ${room.name}`}
                        >
                          Archive
                        </button>
                      </div>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : null}
        </section>

        <section
          className="rounded-2xl border border-white/10 bg-white/[0.06] p-5 shadow-xl shadow-black/20 sm:p-6 lg:sticky lg:top-6"
          aria-labelledby="room-form-heading"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-300">
                {editingId ? "Editing room" : "New room"}
              </p>
              <h2
                id="room-form-heading"
                className="mt-1 text-xl font-bold text-white"
              >
                {editingId ? "Update room details" : "Create a room"}
              </h2>
            </div>
            {editingId ? (
              <button
                type="button"
                onClick={resetForm}
                className="rounded-lg px-2 py-1 text-sm font-medium text-slate-400 hover:bg-white/10 hover:text-white"
              >
                Cancel
              </button>
            ) : null}
          </div>

          <form
            onSubmit={(event) => void handleSubmit(event)}
            className="mt-6 space-y-4"
          >
            <div>
              <label
                htmlFor="room-name"
                className="text-sm font-semibold text-slate-200"
              >
                Name
              </label>
              <input
                id="room-name"
                required
                value={draft.name}
                onChange={(event) =>
                  setDraft({ ...draft, name: event.target.value })
                }
                className="mt-2 min-h-11 w-full rounded-xl border border-white/15 bg-slate-950/60 px-3 text-white outline-none transition focus:border-violet-400 focus:ring-4 focus:ring-violet-500/15"
              />
            </div>

            <div>
              <label
                htmlFor="room-description"
                className="text-sm font-semibold text-slate-200"
              >
                Description
              </label>
              <textarea
                id="room-description"
                required
                rows={3}
                value={draft.description}
                onChange={(event) =>
                  setDraft({ ...draft, description: event.target.value })
                }
                className="mt-2 w-full resize-y rounded-xl border border-white/15 bg-slate-950/60 px-3 py-2.5 text-white outline-none transition focus:border-violet-400 focus:ring-4 focus:ring-violet-500/15"
              />
            </div>

            <div>
              <label
                htmlFor="room-category"
                className="text-sm font-semibold text-slate-200"
              >
                Category
              </label>
              <select
                id="room-category"
                value={draft.category}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    category: event.target.value as RoomCategory,
                  })
                }
                className="mt-2 min-h-11 w-full rounded-xl border border-white/15 bg-slate-950 px-3 text-white outline-none transition focus:border-violet-400 focus:ring-4 focus:ring-violet-500/15"
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {formatCategory(category)}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="room-latitude"
                  className="text-sm font-semibold text-slate-200"
                >
                  Latitude
                </label>
                <input
                  id="room-latitude"
                  type="number"
                  inputMode="decimal"
                  min={-90}
                  max={90}
                  step="any"
                  required
                  value={draft.latitude}
                  onChange={(event) =>
                    setDraft({ ...draft, latitude: event.target.value })
                  }
                  className="mt-2 min-h-11 w-full rounded-xl border border-white/15 bg-slate-950/60 px-3 text-white outline-none transition focus:border-violet-400 focus:ring-4 focus:ring-violet-500/15"
                />
              </div>
              <div>
                <label
                  htmlFor="room-longitude"
                  className="text-sm font-semibold text-slate-200"
                >
                  Longitude
                </label>
                <input
                  id="room-longitude"
                  type="number"
                  inputMode="decimal"
                  min={-180}
                  max={180}
                  step="any"
                  required
                  value={draft.longitude}
                  onChange={(event) =>
                    setDraft({ ...draft, longitude: event.target.value })
                  }
                  className="mt-2 min-h-11 w-full rounded-xl border border-white/15 bg-slate-950/60 px-3 text-white outline-none transition focus:border-violet-400 focus:ring-4 focus:ring-violet-500/15"
                />
              </div>
            </div>

            {formError ? (
              <div
                role="alert"
                className="rounded-xl border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-100"
              >
                {formError}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={isSaving}
              className="min-h-11 w-full rounded-xl bg-violet-500 px-4 text-sm font-bold text-white transition hover:bg-violet-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-300 disabled:cursor-wait disabled:opacity-60"
            >
              {isSaving
                ? editingId
                  ? "Saving changes…"
                  : "Creating room…"
                : editingId
                  ? "Save changes"
                  : "Create room"}
            </button>
          </form>
        </section>
      </div>

      {archiveCandidate ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/80 px-5 backdrop-blur-sm">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="archive-room-heading"
            aria-describedby="archive-room-description"
            className="w-full max-w-md rounded-3xl border border-white/10 bg-slate-900 p-6 shadow-2xl"
          >
            <h2
              id="archive-room-heading"
              className="text-xl font-bold text-white"
            >
              Archive {archiveCandidate.name}?
            </h2>
            <p
              id="archive-room-description"
              className="mt-3 text-sm leading-6 text-slate-300"
            >
              Students will no longer be able to find or join this room. Its
              history will be kept, and the room will remain visible in this
              admin list.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                disabled={isArchiving}
                onClick={() => setArchiveCandidate(null)}
                className="min-h-11 rounded-xl border border-white/15 px-4 text-sm font-semibold text-white hover:bg-white/10 disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isArchiving}
                onClick={() => void handleArchive()}
                className="min-h-11 rounded-xl bg-rose-500 px-4 text-sm font-bold text-white hover:bg-rose-400 disabled:cursor-wait disabled:opacity-60"
              >
                {isArchiving ? "Archiving…" : "Archive room"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
