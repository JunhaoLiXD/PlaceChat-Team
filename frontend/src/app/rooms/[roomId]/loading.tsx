export default function Loading() {
  return (
    <main className="grid min-h-screen place-items-center px-5">
      <div className="flex items-center gap-3 text-sm font-medium text-slate-500">
        <span
          className="h-5 w-5 animate-spin rounded-full border-2 border-violet-200 border-t-violet-600"
          aria-hidden="true"
        />
        Joining room…
      </div>
    </main>
  );
}
