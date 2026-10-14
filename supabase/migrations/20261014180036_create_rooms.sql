create table public.rooms (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    description text not null,
    category text not null check (
        category in ('library', 'dining', 'student life', 'academic', 'recreation')
    ),
    latitude double precision not null check (latitude between -90 and 90),
    longitude double precision not null check (longitude between -180 and 180),
    status text not null default 'active' check (status in ('active', 'archived')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Browsers (including anonymous signed-in users) cannot access rooms directly.
alter table public.rooms enable row level security;
-- Intentionally no policies: rooms are accessed only through FastAPI.

create function public.set_rooms_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger rooms_updated_at
before update on public.rooms
for each row execute function public.set_rooms_updated_at();
