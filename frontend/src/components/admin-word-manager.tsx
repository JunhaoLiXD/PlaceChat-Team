"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import {
  addBlockedWord,
  ApiRequestError,
  deleteBlockedWord,
  listBlockedWords,
} from "@/lib/placechat-api";
import type { BlockedWord } from "@/lib/placechat-types";

type LoadState = "loading" | "ready" | "failed" | "unauthorized";

function sortWords(words: BlockedWord[]): BlockedWord[] {
  return [...words].sort((left, right) => left.word.localeCompare(right.word));
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

/** Admin Words page (PBI-37, Technical Design §2.2 D3, §7.4). */
export function AdminWordManager() {
  const [words, setWords] = useState<BlockedWord[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const handleFailure = (caught: unknown, show: (message: string) => void) => {
    if (isUnauthorized(caught)) {
      setLoadState("unauthorized");
    } else {
      show(errorMessage(caught));
    }
  };

  const load = async () => {
    setLoadState("loading");
    setLoadError(null);
    try {
      setWords(sortWords(await listBlockedWords()));
      setLoadState("ready");
    } catch (caught) {
      handleFailure(caught, (message) => {
        setLoadError(message);
        setLoadState("failed");
      });
    }
  };

  useEffect(() => {
    let cancelled = false;

    listBlockedWords().then(
      (nextWords) => {
        if (cancelled) return;
        setWords(sortWords(nextWords));
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

  const trimmedDraft = draft.trim();

  const handleAdd = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!trimmedDraft || isSaving) return;
    setFormError(null);
    setSuccess(null);
    setIsSaving(true);

    try {
      const added = await addBlockedWord(trimmedDraft);
      setWords((current) => sortWords([...current, added]));
      setDraft("");
      setSuccess(`Added "${added.word}". It applies to the next message.`);
    } catch (caught) {
      handleFailure(caught, setFormError);
    } finally {
      setIsSaving(false);
    }
  };

  const handleRemove = async (word: BlockedWord) => {
    if (removingId) return;
    setFormError(null);
    setSuccess(null);
    setRemovingId(word.id);

    try {
      await deleteBlockedWord(word.id);
      setWords((current) => current.filter((item) => item.id !== word.id));
      setSuccess(`Removed "${word.word}".`);
    } catch (caught) {
      handleFailure(caught, setFormError);
    } finally {
      setRemovingId(null);
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
    <main className="mx-auto w-full max-w-3xl px-5 py-10 sm:px-8 sm:py-12">
      <div className="mb-8">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-violet-300">
          Content safety
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-[-0.045em] text-white sm:text-4xl">
          Blocked words
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
          Words on this list are replaced with asterisks in new messages,
          ignoring upper and lower case. Changes apply to the next message;
          messages already sent are not changed.
        </p>
      </div>

      <form
        onSubmit={(event) => void handleAdd(event)}
        className="rounded-3xl border border-white/10 bg-white/[0.04] p-5 sm:p-6"
      >
        <label
          htmlFor="blocked-word"
          className="text-sm font-semibold text-slate-200"
        >
          Add a word or phrase
        </label>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row">
          <input
            id="blocked-word"
            name="word"
            type="text"
            autoComplete="off"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="min-h-12 w-full rounded-xl border border-white/15 bg-slate-950/70 px-4 text-base text-white outline-none transition placeholder:text-slate-600 focus:border-violet-400 focus:ring-4 focus:ring-violet-500/15"
            placeholder="for example: badword"
          />
          <button
            type="submit"
            disabled={!trimmedDraft || isSaving}
            className="min-h-12 shrink-0 rounded-xl bg-violet-500 px-6 text-sm font-bold text-white shadow-lg shadow-violet-950/50 transition hover:bg-violet-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving ? "Adding…" : "Add"}
          </button>
        </div>
        {formError ? (
          <p
            role="alert"
            className="mt-3 rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm leading-5 text-rose-100"
          >
            {formError}
          </p>
        ) : null}
      </form>

      <p role="status" className="mt-4 min-h-5 text-sm text-emerald-300">
        {success ?? ""}
      </p>

      <section aria-labelledby="word-list-heading" className="mt-4">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 id="word-list-heading" className="text-lg font-bold text-white">
            On the list
          </h2>
          {loadState === "ready" ? (
            <span className="text-sm text-slate-400">
              {words.length} {words.length === 1 ? "word" : "words"}
            </span>
          ) : null}
        </div>

        {loadState === "loading" ? (
          <p className="text-sm text-slate-400">Loading blocked words…</p>
        ) : null}

        {loadState === "failed" ? (
          <div
            role="alert"
            className="rounded-2xl border border-rose-400/30 bg-rose-500/10 p-4 text-sm text-rose-100"
          >
            <p>{loadError}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="mt-3 min-h-10 rounded-lg border border-white/15 px-3 font-semibold text-white transition hover:bg-white/10"
            >
              Retry
            </button>
          </div>
        ) : null}

        {loadState === "ready" && words.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-white/15 p-6 text-center text-sm text-slate-400">
            No blocked words yet.
          </p>
        ) : null}

        {loadState === "ready" && words.length > 0 ? (
          <ul className="divide-y divide-white/10 overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03]">
            {words.map((word) => (
              <li
                key={word.id}
                className="flex items-center justify-between gap-3 px-4 py-3"
              >
                <span className="min-w-0 break-words font-mono text-sm text-white">
                  {word.word}
                </span>
                <button
                  type="button"
                  aria-label={`Remove ${word.word}`}
                  disabled={removingId !== null}
                  onClick={() => void handleRemove(word)}
                  className="min-h-10 shrink-0 rounded-lg border border-white/15 px-3 text-sm font-semibold text-slate-200 transition hover:border-rose-400/40 hover:bg-rose-500/10 hover:text-rose-100 disabled:cursor-wait disabled:opacity-50"
                >
                  {removingId === word.id ? "Removing…" : "Remove"}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </main>
  );
}
