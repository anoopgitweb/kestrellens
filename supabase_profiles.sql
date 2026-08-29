-- Run once in the Supabase SQL editor for the KestrelIQ project.
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  full_name text not null default '',
  company text not null default '',
  stock_symbol text not null default '',
  tool_access jsonb not null default '[]'::jsonb,
  openai_enabled boolean not null default false,
  notebook_access boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles add column if not exists email text;
alter table public.profiles add column if not exists full_name text not null default '';
alter table public.profiles add column if not exists company text not null default '';
alter table public.profiles add column if not exists stock_symbol text not null default '';
alter table public.profiles add column if not exists tool_access jsonb not null default '[]'::jsonb;
alter table public.profiles add column if not exists openai_enabled boolean not null default false;
alter table public.profiles add column if not exists notebook_access boolean not null default false;
alter table public.profiles add column if not exists created_at timestamptz not null default now();
alter table public.profiles add column if not exists updated_at timestamptz not null default now();

alter table public.profiles enable row level security;

drop policy if exists "Users can read their profile" on public.profiles;
create policy "Users can read their profile"
  on public.profiles for select
  using (auth.uid() = id);

drop policy if exists "Users can create their profile" on public.profiles;
create policy "Users can create their profile"
  on public.profiles for insert
  with check (auth.uid() = id);

drop policy if exists "Users can update their profile" on public.profiles;
create policy "Users can update their profile"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);
