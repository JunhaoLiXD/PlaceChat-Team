import { AppHeader } from "@/components/app-header";
import { RoomDirectory } from "@/components/room-directory";

export default function Home() {
  return (
    <main className="min-h-screen pb-16">
      <AppHeader />

      <section className="mx-auto w-full max-w-6xl px-5 pb-8 pt-12 sm:px-8 sm:pt-16">
        <div className="max-w-3xl">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-violet-200 bg-white/80 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] text-violet-700 shadow-sm">
            <span
              className="h-2 w-2 rounded-full bg-emerald-500"
              aria-hidden="true"
            />
            Live around campus
          </div>
          <h1 className="text-balance text-4xl font-bold tracking-[-0.045em] text-slate-950 sm:text-6xl">
            Find your place.
            <span className="block text-violet-600">
              Join the conversation.
            </span>
          </h1>
          <p className="mt-5 max-w-2xl text-pretty text-base leading-7 text-slate-600 sm:text-lg">
            Drop into anonymous chats for the places you already know. No
            profile, no pressure—just the people around campus right now.
          </p>
        </div>
      </section>

      <RoomDirectory />
    </main>
  );
}
