"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { signInWithPassword, signOutAdmin } from "@/lib/admin-auth";
import { ApiRequestError, listAdminRooms } from "@/lib/placechat-api";

const NOT_AUTHORIZED =
  "Not authorized. This account does not have administrator access.";

export function AdminLoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await signInWithPassword(email.trim(), password);
      await listAdminRooms();
      router.replace("/admin/rooms");
    } catch (caught) {
      if (
        caught instanceof ApiRequestError &&
        (caught.status === 401 || caught.status === 403)
      ) {
        try {
          await signOutAdmin();
        } catch {
          // The authorization result is still authoritative; a later sign-in replaces the session.
        }
        setError(NOT_AUTHORIZED);
      } else if (caught instanceof ApiRequestError) {
        setError(caught.message);
      } else {
        setError(
          "Sign-in failed. Check your email and password and try again.",
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="relative isolate grid min-h-[calc(100vh-4rem)] place-items-center overflow-hidden px-5 py-12 sm:px-8">
      <div
        className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_20%_20%,rgba(124,58,237,0.28),transparent_28rem),radial-gradient(circle_at_85%_70%,rgba(14,165,233,0.16),transparent_24rem)]"
        aria-hidden="true"
      />

      <section className="w-full max-w-md rounded-3xl border border-white/10 bg-white/[0.07] p-6 shadow-2xl shadow-black/30 backdrop-blur-xl sm:p-8">
        <div className="mb-8">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-violet-300">
            Restricted access
          </p>
          <h1 className="mt-3 text-3xl font-bold tracking-[-0.04em] text-white">
            Administrator sign in
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            Use the email and password for your provisioned PlaceChat admin
            account.
          </p>
        </div>

        <form
          onSubmit={(event) => void handleSubmit(event)}
          className="space-y-5"
        >
          <div>
            <label
              htmlFor="admin-email"
              className="text-sm font-semibold text-slate-200"
            >
              Email
            </label>
            <input
              id="admin-email"
              name="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-2 min-h-12 w-full rounded-xl border border-white/15 bg-slate-950/70 px-4 text-base text-white outline-none transition placeholder:text-slate-600 focus:border-violet-400 focus:ring-4 focus:ring-violet-500/15"
              placeholder="admin@example.edu"
            />
          </div>

          <div>
            <label
              htmlFor="admin-password"
              className="text-sm font-semibold text-slate-200"
            >
              Password
            </label>
            <input
              id="admin-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-2 min-h-12 w-full rounded-xl border border-white/15 bg-slate-950/70 px-4 text-base text-white outline-none transition focus:border-violet-400 focus:ring-4 focus:ring-violet-500/15"
            />
          </div>

          {error ? (
            <div
              role="alert"
              className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm leading-5 text-rose-100"
            >
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex min-h-12 w-full items-center justify-center rounded-xl bg-violet-500 px-4 text-sm font-bold text-white shadow-lg shadow-violet-950/50 transition hover:bg-violet-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-300 disabled:cursor-wait disabled:opacity-60"
          >
            {isSubmitting ? "Checking access…" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
