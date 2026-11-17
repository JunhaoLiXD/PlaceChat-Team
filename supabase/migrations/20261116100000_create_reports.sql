-- Message reports (PlaceChat Technical Design §5.1, §7.1).
create table public.reports (
    id uuid primary key default gen_random_uuid(),
    message_id uuid not null references public.messages (id),
    room_id uuid not null references public.rooms (id),
    reporter_session_id uuid not null,
    reason text check (reason in ('harassment', 'spam', 'other')),
    status text not null default 'pending' check (status in ('pending', 'removed', 'dismissed')),
    created_at timestamptz not null default now(),
    handled_at timestamptz,
    handled_by uuid,
    unique (message_id, reporter_session_id)
);

create index reports_status_created_at_idx on public.reports (status, created_at);

alter table public.reports enable row level security;
-- Intentionally no policies: reports are accessed only through FastAPI.
