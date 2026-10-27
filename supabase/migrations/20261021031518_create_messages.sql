-- Chat messages (PlaceChat Technical Design §4, §5.1).
--
-- session_id is the Supabase anonymous user id. It is never sent to browsers (§4), and it has no
-- foreign key to auth.users, so messages stay on record even if Supabase cleans up old anonymous
-- users. removed_at / removed_by are set when an admin removes a message (E2); nothing is
-- hard-deleted. The 500-character limit is a backend setting (§11), so it is not repeated here.
create table public.messages (
    id uuid primary key default gen_random_uuid(),
    room_id uuid not null references public.rooms (id),
    session_id uuid not null,
    nickname text not null,
    body text not null check (body <> ''),
    created_at timestamptz not null default now(),
    removed_at timestamptz,
    removed_by uuid,
    check ((removed_at is null) = (removed_by is null))
);

-- Room history: newest visible messages per room (§5.2).
create index messages_room_id_created_at_idx on public.messages (room_id, created_at);
-- Rate limit: one session's messages in the last 10 seconds (§5.2).
create index messages_session_id_created_at_idx on public.messages (session_id, created_at);

-- Browsers (including anonymous signed-in users) cannot access messages directly.
alter table public.messages enable row level security;
-- Intentionally no policies: messages are accessed only through FastAPI.
