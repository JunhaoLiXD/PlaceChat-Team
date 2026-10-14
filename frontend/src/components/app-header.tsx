import Link from "next/link";

export function AppHeader() {
  return (
    <header className="border-b border-slate-200/80 bg-white/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-5 sm:px-8">
        <Link
          href="/"
          className="group inline-flex items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-violet-600"
        >
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-violet-600 text-sm font-black text-white shadow-md shadow-violet-200 transition-transform group-hover:-rotate-3">
            P
          </span>
          <span className="text-lg font-bold tracking-[-0.03em] text-slate-950">
            PlaceChat
          </span>
        </Link>

        <div className="flex items-center gap-2 text-xs font-medium text-slate-500 sm:text-sm">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            className="h-4 w-4 text-violet-600"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16.5 10.5V6.75a4.5 4.5 0 0 0-9 0v3.75m-.75 0h10.5a1.5 1.5 0 0 1 1.5 1.5v7.5H5.25V12a1.5 1.5 0 0 1 1.5-1.5Z"
            />
          </svg>
          No account needed
        </div>
      </div>
    </header>
  );
}
