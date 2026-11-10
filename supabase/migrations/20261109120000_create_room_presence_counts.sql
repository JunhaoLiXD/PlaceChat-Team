-- Change detection only: presence remains left_at IS NULL and last_seen_at >= cutoff.
-- Keeping this separate avoids changing room metadata or membership/nickname holds.
create table public.room_presence_counts (
    room_id uuid primary key references public.rooms(id) on delete cascade,
    participant_count integer not null check (participant_count >= 0)
);

alter table public.room_presence_counts enable row level security;
-- Intentionally no policies: only FastAPI can observe and update these snapshots.
