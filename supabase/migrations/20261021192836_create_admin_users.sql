-- Administrator allow-list (PlaceChat Technical Design §5.1, §6.2).
-- Junhao provisions Supabase email/password accounts and their allow-list entries.
create table public.admin_users (
    user_id uuid primary key references auth.users(id) on delete cascade,
    display_name text not null,
    created_at timestamptz not null default now()
);

alter table public.admin_users enable row level security;
-- Intentionally no policies: browsers cannot read, grant, or modify admin privileges.
