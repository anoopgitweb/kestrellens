-- Run once in the Supabase SQL editor for the KestrelIQ project.
create extension if not exists pgcrypto;

create table if not exists public.watchlists (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  mode text not null default 'companies' check (mode in ('companies', 'people', 'interests')),
  items jsonb not null default '[]'::jsonb check (jsonb_typeof(items) = 'array'),
  is_active boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, name)
);

create index if not exists watchlists_user_updated_idx
  on public.watchlists (user_id, updated_at desc);

alter table public.watchlists enable row level security;

drop policy if exists "Users can read their watchlists" on public.watchlists;
create policy "Users can read their watchlists"
  on public.watchlists for select
  using (auth.uid() = user_id);

drop policy if exists "Users can create their watchlists" on public.watchlists;
create policy "Users can create their watchlists"
  on public.watchlists for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users can update their watchlists" on public.watchlists;
create policy "Users can update their watchlists"
  on public.watchlists for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "Users can delete their watchlists" on public.watchlists;
create policy "Users can delete their watchlists"
  on public.watchlists for delete
  using (auth.uid() = user_id);
