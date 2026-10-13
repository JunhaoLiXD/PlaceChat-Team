import Link from "next/link";

export default function RoomNotFound() {
  return (
    <main className="grid min-h-screen place-items-center px-5">
      <section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-xl shadow-slate-200/60">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-violet-100 text-2xl">
          💬
        </div>
        <h1 className="mt-5 text-2xl font-bold tracking-tight text-slate-950">
          Room not found
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          This room may have closed or moved. Pick another campus conversation
          to join.
        </p>
        <Link
          href="/"
          className="mt-6 inline-flex min-h-11 items-center justify-center rounded-xl bg-violet-600 px-5 text-sm font-semibold text-white transition hover:bg-violet-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600"
        >
          Browse rooms
        </Link>
      </section>
    </main>
  );
}
