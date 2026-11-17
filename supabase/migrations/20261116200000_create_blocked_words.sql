-- Configurable blocked words for outgoing message filtering (PBI-36).
create table public.blocked_words (
    id uuid primary key default gen_random_uuid(),
    word text not null unique check (word = lower(word) and word <> ''),
    created_at timestamptz not null default now()
);

alter table public.blocked_words enable row level security;
-- Intentionally no policies: blocked words are accessed only through FastAPI.
