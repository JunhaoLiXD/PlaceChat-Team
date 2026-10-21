create table public.room_members (
    room_id uuid not null references public.rooms(id),
    session_id uuid not null references auth.users(id) on delete cascade,
    nickname text not null,
    joined_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    left_at timestamptz,
    primary key (room_id, session_id)
);

create index room_members_reservations_idx
on public.room_members (room_id, last_seen_at)
where left_at is null;

alter table public.room_members enable row level security;
-- Intentionally no policies: browsers access membership only through FastAPI.
