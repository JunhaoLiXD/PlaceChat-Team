-- Temporary sender blocks across all rooms (PlaceChat Technical Design §5.1, E3).
-- Session and administrator IDs stay on record even if an Auth user is cleaned up.
create table public.blocks (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null,
    reason text,
    created_by uuid not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    check (expires_at > created_at)
);

create index blocks_session_id_expires_at_idx on public.blocks (session_id, expires_at);

alter table public.blocks enable row level security;
-- Intentionally no policies: blocks are accessed only through FastAPI.
