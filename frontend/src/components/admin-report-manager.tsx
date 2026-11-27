"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ADMIN_SIGNED_OUT_EVENT } from "@/lib/admin-auth";
import {
  ApiRequestError,
  blockReportedSender,
  dismissAdminReport,
  listAdminReports,
  removeReportedMessage,
} from "@/lib/placechat-api";
import type { AdminReport, BlockDurationMinutes } from "@/lib/placechat-types";

export const ADMIN_REPORT_REFRESH_MS = 30_000;

const BLOCK_DURATIONS = [
  { minutes: 15, label: "15 minutes" },
  { minutes: 60, label: "1 hour" },
  { minutes: 1440, label: "24 hours" },
] as const satisfies ReadonlyArray<{
  minutes: BlockDurationMinutes;
  label: string;
}>;

type ReportAction =
  | { type: "remove" | "dismiss" }
  | { type: "block"; durationMinutes: BlockDurationMinutes };

const REASON_LABELS: Record<NonNullable<AdminReport["reason"]>, string> = {
  harassment: "Harassment",
  spam: "Spam",
  other: "Other",
};

function formatReportTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/New_York",
  }).format(new Date(value));
}

function errorMessage(caught: unknown) {
  return caught instanceof Error
    ? caught.message
    : "We couldn't update the report queue.";
}

export function AdminReportManager() {
  const [reports, setReports] = useState<AdminReport[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [blockSelection, setBlockSelection] = useState<{
    reportId: string;
    durationMinutes: BlockDurationMinutes;
  } | null>(null);
  const [notAuthorized, setNotAuthorized] = useState(false);
  const [busyAction, setBusyAction] = useState<{
    reportId: string;
    action: ReportAction["type"];
  } | null>(null);
  const mountedRef = useRef(false);
  const latestRequestRef = useRef(0);
  const actionVersionRef = useRef(0);

  const loadReports = useCallback(async () => {
    const requestId = ++latestRequestRef.current;

    try {
      const nextReports = await listAdminReports();
      if (!mountedRef.current || requestId !== latestRequestRef.current) return;
      setReports(nextReports);
      setLoadError(null);
      setNotAuthorized(false);
    } catch (caught) {
      if (!mountedRef.current || requestId !== latestRequestRef.current) return;
      if (
        caught instanceof ApiRequestError &&
        (caught.status === 401 || caught.status === 403)
      ) {
        setNotAuthorized(true);
      } else {
        setLoadError(errorMessage(caught));
      }
    } finally {
      if (mountedRef.current && requestId === latestRequestRef.current) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const handleAdminSignOut = () => {
      latestRequestRef.current += 1;
      actionVersionRef.current += 1;
      setReports([]);
      setLoadError(null);
      setActionError(null);
      setActionSuccess(null);
      setBlockSelection(null);
      setBusyAction(null);
      setNotAuthorized(false);
      setIsLoading(true);
      setIsRefreshing(false);
      void loadReports();
    };
    const initialRequest = window.setTimeout(() => {
      // Activity preserves state, but the previous visit no longer owns an action.
      setBusyAction(null);
      void loadReports();
    }, 0);
    const interval = window.setInterval(() => {
      setIsRefreshing(true);
      void loadReports();
    }, ADMIN_REPORT_REFRESH_MS);
    window.addEventListener(ADMIN_SIGNED_OUT_EVENT, handleAdminSignOut);

    return () => {
      mountedRef.current = false;
      latestRequestRef.current += 1;
      actionVersionRef.current += 1;
      window.clearTimeout(initialRequest);
      window.clearInterval(interval);
      window.removeEventListener(ADMIN_SIGNED_OUT_EVENT, handleAdminSignOut);
    };
  }, [loadReports]);

  const handleAction = async (report: AdminReport, action: ReportAction) => {
    if (busyAction) return;
    const version = actionVersionRef.current;
    const isCurrent = () =>
      mountedRef.current && version === actionVersionRef.current;
    setBusyAction({ reportId: report.id, action: action.type });
    setActionError(null);
    setActionSuccess(null);

    try {
      if (action.type === "block") {
        const block = await blockReportedSender(
          report.id,
          action.durationMinutes,
        );
        if (!isCurrent()) return;
        setBlockSelection(null);
        setActionSuccess(
          `${report.message.nickname} is blocked from sending in all rooms until ${formatReportTime(block.expires_at)} Eastern Time.`,
        );
      } else if (action.type === "remove") {
        await removeReportedMessage(report.id);
        if (!isCurrent()) return;
        setReports((current) =>
          current.filter(
            (candidate) => candidate.message.id !== report.message.id,
          ),
        );
      } else {
        await dismissAdminReport(report.id);
        if (!isCurrent()) return;
        setReports((current) =>
          current.filter((candidate) => candidate.id !== report.id),
        );
      }
    } catch (caught) {
      if (!isCurrent()) return;
      if (
        caught instanceof ApiRequestError &&
        (caught.status === 401 || caught.status === 403)
      ) {
        setNotAuthorized(true);
      } else if (caught instanceof ApiRequestError && caught.status === 404) {
        setBlockSelection(null);
        if (action.type === "block")
          setActionError(
            "This report is no longer available. Refreshing the queue.",
          );
        setIsRefreshing(true);
        void loadReports();
      } else {
        setActionError(errorMessage(caught));
      }
    } finally {
      if (isCurrent()) setBusyAction(null);
    }
  };

  if (notAuthorized) {
    return (
      <main className="mx-auto grid min-h-[calc(100vh-4rem)] w-full max-w-3xl place-items-center px-5 py-12 sm:px-8">
        <section className="w-full rounded-3xl border border-rose-400/20 bg-rose-500/10 p-8 text-center">
          <h1 className="text-2xl font-bold text-white">Not authorized</h1>
          <p role="alert" className="mt-3 text-sm leading-6 text-rose-100">
            This page is only available to provisioned PlaceChat administrators.
          </p>
          <Link
            href="/admin/login"
            className="mt-6 inline-flex min-h-11 items-center rounded-xl bg-white px-4 text-sm font-bold text-slate-950 transition hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            Return to admin sign in
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-violet-300">
            Moderation queue
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-[-0.04em] text-white">
            Pending reports
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            Review messages reported by participants. The queue refreshes every
            30 seconds.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isRefreshing ? (
            <span role="status" className="text-xs text-slate-400">
              Refreshing…
            </span>
          ) : null}
          <span className="rounded-full border border-white/10 bg-white/[0.07] px-3 py-1.5 text-sm font-bold text-white">
            {reports.length} pending
          </span>
        </div>
      </div>

      {loadError ? (
        <div
          role="alert"
          className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-400/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-100"
        >
          <span>{loadError}</span>
          <button
            type="button"
            onClick={() => {
              setIsLoading(true);
              void loadReports();
            }}
            className="min-h-9 rounded-lg bg-rose-100 px-3 text-xs font-bold text-rose-950 focus-visible:outline-2 focus-visible:outline-white"
          >
            Try again
          </button>
        </div>
      ) : null}

      {actionError ? (
        <p
          role="alert"
          className="mt-6 rounded-2xl border border-rose-400/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-100"
        >
          {actionError}
        </p>
      ) : null}

      {actionSuccess ? (
        <p
          role="status"
          className="mt-6 rounded-2xl border border-emerald-400/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100"
        >
          {actionSuccess}
        </p>
      ) : null}

      {isLoading ? (
        <div aria-label="Loading reports" className="mt-8 space-y-4">
          {Array.from({ length: 3 }, (_, index) => (
            <div
              key={index}
              className="h-48 animate-pulse rounded-3xl border border-white/10 bg-white/[0.05]"
            />
          ))}
        </div>
      ) : reports.length === 0 && !loadError ? (
        <section className="mt-8 rounded-3xl border border-dashed border-white/15 bg-white/[0.04] p-12 text-center">
          <h2 className="text-lg font-bold text-white">Queue cleared</h2>
          <p className="mt-2 text-sm text-slate-400">
            There are no pending reports right now.
          </p>
        </section>
      ) : (
        <ol className="mt-8 space-y-4">
          {reports.map((report) => {
            const isBusy = busyAction?.reportId === report.id;
            return (
              <li key={report.id}>
                <article className="rounded-3xl border border-white/10 bg-white/[0.06] p-5 shadow-xl shadow-black/10 sm:p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-white">
                        {report.message.nickname}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">
                        {report.room.name} /{" "}
                        <time dateTime={report.message.created_at}>
                          {formatReportTime(report.message.created_at)}
                        </time>
                      </p>
                    </div>
                    <span className="rounded-full bg-amber-400/10 px-3 py-1 text-xs font-semibold text-amber-200 ring-1 ring-inset ring-amber-300/20">
                      {report.reason
                        ? REASON_LABELS[report.reason]
                        : "No reason"}
                    </span>
                  </div>

                  <blockquote className="mt-4 whitespace-pre-wrap break-words rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm leading-6 text-slate-200">
                    {report.message.body}
                  </blockquote>

                  <div className="mt-5 grid gap-2 sm:grid-cols-3">
                    <button
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() =>
                        void handleAction(report, { type: "remove" })
                      }
                      aria-label={`Remove message from ${report.message.nickname}`}
                      className="min-h-11 rounded-xl bg-rose-500 px-4 text-sm font-bold text-white transition hover:bg-rose-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-300 disabled:cursor-wait disabled:opacity-60"
                    >
                      {isBusy && busyAction.action === "remove"
                        ? "Removing…"
                        : "Remove message"}
                    </button>
                    <button
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() =>
                        void handleAction(report, { type: "dismiss" })
                      }
                      aria-label={`Dismiss report for ${report.message.nickname}`}
                      className="min-h-11 rounded-xl border border-white/15 px-4 text-sm font-bold text-white transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-violet-300 disabled:cursor-wait disabled:opacity-60"
                    >
                      {isBusy && busyAction.action === "dismiss"
                        ? "Dismissing…"
                        : "Dismiss"}
                    </button>
                    <button
                      type="button"
                      disabled={busyAction !== null}
                      aria-label={`Block sender ${report.message.nickname}`}
                      aria-expanded={blockSelection?.reportId === report.id}
                      aria-controls={`block-${report.id}`}
                      onClick={() => {
                        setActionError(null);
                        setActionSuccess(null);
                        setBlockSelection((current) =>
                          current?.reportId === report.id
                            ? null
                            : { reportId: report.id, durationMinutes: 15 },
                        );
                      }}
                      className="min-h-11 rounded-xl border border-amber-300/25 bg-amber-400/10 px-4 text-sm font-bold text-amber-100 transition hover:bg-amber-400/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300 disabled:cursor-wait disabled:opacity-60"
                    >
                      Block sender
                    </button>
                  </div>
                  {blockSelection?.reportId === report.id ? (
                    <form
                      id={`block-${report.id}`}
                      aria-label={`Block ${report.message.nickname}`}
                      onSubmit={(event) => {
                        event.preventDefault();
                        void handleAction(report, {
                          type: "block",
                          durationMinutes: blockSelection.durationMinutes,
                        });
                      }}
                      className="mt-4 rounded-2xl border border-amber-300/20 bg-slate-950/40 p-4"
                    >
                      <p className="text-sm leading-6 text-slate-300">
                        Prevent this sender from posting in every room. Blocks
                        cannot be lifted early. The message and report stay in
                        the queue for review.
                      </p>
                      <label
                        htmlFor={`duration-${report.id}`}
                        className="mt-3 block text-sm font-semibold text-white"
                      >
                        Block duration
                      </label>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <select
                          id={`duration-${report.id}`}
                          value={blockSelection.durationMinutes}
                          disabled={busyAction !== null}
                          onChange={(event) => {
                            const duration = BLOCK_DURATIONS.find(
                              (option) =>
                                option.minutes === Number(event.target.value),
                            );
                            if (duration)
                              setBlockSelection({
                                reportId: report.id,
                                durationMinutes: duration.minutes,
                              });
                          }}
                          className="min-h-11 rounded-xl border border-white/15 bg-slate-900 px-3 text-sm text-white focus-visible:outline-2 focus-visible:outline-amber-300 disabled:opacity-60"
                        >
                          {BLOCK_DURATIONS.map((duration) => (
                            <option
                              key={duration.minutes}
                              value={duration.minutes}
                            >
                              {duration.label}
                            </option>
                          ))}
                        </select>
                        <button
                          type="submit"
                          disabled={busyAction !== null}
                          className="min-h-11 rounded-xl bg-amber-300 px-4 text-sm font-bold text-slate-950 transition hover:bg-amber-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300 disabled:cursor-wait disabled:opacity-60"
                        >
                          {isBusy && busyAction.action === "block"
                            ? "Blocking…"
                            : "Confirm block"}
                        </button>
                        <button
                          type="button"
                          disabled={busyAction !== null}
                          onClick={() => setBlockSelection(null)}
                          className="min-h-11 rounded-xl border border-white/15 px-4 text-sm font-semibold text-white hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white disabled:opacity-60"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  ) : null}
                </article>
              </li>
            );
          })}
        </ol>
      )}
    </main>
  );
}
