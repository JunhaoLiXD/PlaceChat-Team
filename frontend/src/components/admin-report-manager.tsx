"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiRequestError,
  dismissAdminReport,
  listAdminReports,
  removeReportedMessage,
} from "@/lib/placechat-api";
import type { AdminReport } from "@/lib/placechat-types";

export const ADMIN_REPORT_REFRESH_MS = 30_000;

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
    : "We couldnâ€™t update the report queue.";
}

export function AdminReportManager() {
  const [reports, setReports] = useState<AdminReport[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notAuthorized, setNotAuthorized] = useState(false);
  const [busyAction, setBusyAction] = useState<{
    reportId: string;
    action: "remove" | "dismiss";
  } | null>(null);
  const mountedRef = useRef(false);
  const latestRequestRef = useRef(0);

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
    const initialRequest = window.setTimeout(() => {
      void loadReports();
    }, 0);
    const interval = window.setInterval(() => {
      setIsRefreshing(true);
      void loadReports();
    }, ADMIN_REPORT_REFRESH_MS);

    return () => {
      mountedRef.current = false;
      latestRequestRef.current += 1;
      window.clearTimeout(initialRequest);
      window.clearInterval(interval);
    };
  }, [loadReports]);

  const handleAction = async (
    report: AdminReport,
    action: "remove" | "dismiss",
  ) => {
    if (busyAction) return;
    setBusyAction({ reportId: report.id, action });
    setActionError(null);

    try {
      if (action === "remove") {
        await removeReportedMessage(report.id);
        setReports((current) =>
          current.filter(
            (candidate) => candidate.message.id !== report.message.id,
          ),
        );
      } else {
        await dismissAdminReport(report.id);
        setReports((current) =>
          current.filter((candidate) => candidate.id !== report.id),
        );
      }
    } catch (caught) {
      if (
        caught instanceof ApiRequestError &&
        (caught.status === 401 || caught.status === 403)
      ) {
        setNotAuthorized(true);
      } else {
        setActionError(errorMessage(caught));
      }
    } finally {
      setBusyAction(null);
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
              Refreshingâ€¦
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
                      onClick={() => void handleAction(report, "remove")}
                      aria-label={`Remove message from ${report.message.nickname}`}
                      className="min-h-11 rounded-xl bg-rose-500 px-4 text-sm font-bold text-white transition hover:bg-rose-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-300 disabled:cursor-wait disabled:opacity-60"
                    >
                      {isBusy && busyAction.action === "remove"
                        ? "Removingâ€¦"
                        : "Remove message"}
                    </button>
                    <button
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() => void handleAction(report, "dismiss")}
                      aria-label={`Dismiss report for ${report.message.nickname}`}
                      className="min-h-11 rounded-xl border border-white/15 px-4 text-sm font-bold text-white transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-violet-300 disabled:cursor-wait disabled:opacity-60"
                    >
                      {isBusy && busyAction.action === "dismiss"
                        ? "Dismissingâ€¦"
                        : "Dismiss"}
                    </button>
                    <button
                      type="button"
                      disabled
                      title="Temporary blocks are added in PBI-42"
                      className="min-h-11 rounded-xl border border-dashed border-white/10 px-4 text-sm font-semibold text-slate-500"
                    >
                      Block sender
                    </button>
                  </div>
                </article>
              </li>
            );
          })}
        </ol>
      )}
    </main>
  );
}
