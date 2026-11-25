"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { signOutAdmin } from "@/lib/admin-auth";

const ADMIN_LINKS = [
  { href: "/admin/rooms", label: "Rooms" },
  { href: "/admin/reports", label: "Reports" },
  { href: "/admin/words", label: "Words" },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const isLogin = pathname === "/admin/login";

  const handleSignOut = async () => {
    setIsSigningOut(true);
    try {
      await signOutAdmin();
    } finally {
      router.replace("/admin/login");
      setIsSigningOut(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-white/10 bg-slate-950/90 backdrop-blur-xl">
        <div className="mx-auto flex min-h-16 w-full max-w-7xl items-center justify-between gap-4 px-5 py-3 sm:px-8">
          <div className="flex min-w-0 items-center gap-5">
            <Link
              href={isLogin ? "/admin/login" : "/admin/rooms"}
              className="group inline-flex items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-violet-400"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-violet-500 text-sm font-black text-white shadow-lg shadow-violet-950 transition-transform group-hover:-rotate-3">
                P
              </span>
              <span className="truncate text-base font-bold tracking-[-0.03em] text-white sm:text-lg">
                PlaceChat <span className="text-violet-300">Admin</span>
              </span>
            </Link>

            {!isLogin ? (
              <nav
                aria-label="Admin navigation"
                className="hidden items-center gap-1 sm:flex"
              >
                {ADMIN_LINKS.map((link) => {
                  const isCurrent = pathname === link.href;
                  return (
                    <Link
                      key={link.href}
                      href={link.href}
                      aria-current={isCurrent ? "page" : undefined}
                      className={`rounded-lg px-3 py-2 text-sm font-semibold transition hover:bg-white/15 focus-visible:outline-2 focus-visible:outline-violet-400 ${
                        isCurrent ? "bg-white/10 text-white" : "text-slate-300"
                      }`}
                    >
                      {link.label}
                    </Link>
                  );
                })}
              </nav>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Link
              href="/"
              className="rounded-lg px-3 py-2 text-sm font-medium text-slate-300 transition hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-violet-400"
            >
              Campus site
            </Link>
            {!isLogin ? (
              <button
                type="button"
                disabled={isSigningOut}
                onClick={() => void handleSignOut()}
                className="min-h-10 rounded-lg border border-white/15 px-3 text-sm font-semibold text-white transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-violet-400 disabled:cursor-wait disabled:opacity-60"
              >
                {isSigningOut ? "Signing out…" : "Sign out"}
              </button>
            ) : null}
          </div>
        </div>
        {!isLogin ? (
          <nav
            aria-label="Admin navigation mobile"
            className="mx-auto flex w-full max-w-7xl border-t border-white/10 px-5 sm:hidden"
          >
            {ADMIN_LINKS.map((link) => {
              const isCurrent = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={isCurrent ? "page" : undefined}
                  className={`flex min-h-11 flex-1 items-center justify-center border-b-2 text-sm font-semibold ${
                    isCurrent
                      ? "border-violet-400 text-white"
                      : "border-transparent text-slate-400"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        ) : null}
      </header>
      {children}
    </div>
  );
}
