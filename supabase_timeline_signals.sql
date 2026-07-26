create extension if not exists pgcrypto;

create table if not exists public.timeline_signals (
  id uuid primary key default gen_random_uuid(),
  headline text not null,
  provider text not null,
  category text not null check (category in ('chips', 'agentic', 'enterprise', 'models', 'risk', 'technology')),
  source text not null,
  url text not null unique,
  summary text not null default '',
  published_at timestamptz not null,
  entry_type text not null default 'manual' check (entry_type in ('manual', 'automatic')),
  created_by uuid references auth.users(id) on delete set null,
  created_by_email text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists timeline_signals_published_at_idx
  on public.timeline_signals (published_at desc);

create index if not exists timeline_signals_provider_idx
  on public.timeline_signals (provider);

create index if not exists timeline_signals_category_idx
  on public.timeline_signals (category);

alter table public.timeline_signals enable row level security;

drop policy if exists "Timeline signals are readable by everyone" on public.timeline_signals;
create policy "Timeline signals are readable by everyone"
  on public.timeline_signals
  for select
  to anon, authenticated
  using (true);

drop policy if exists "Timeline admin can add signals" on public.timeline_signals;
create policy "Timeline admin can add signals"
  on public.timeline_signals
  for insert
  to authenticated
  with check (
    lower(coalesce(auth.jwt() ->> 'email', '')) = 'anoopviswanathan@outlook.com'
    and created_by = auth.uid()
  );

drop policy if exists "Timeline admin can update signals" on public.timeline_signals;
create policy "Timeline admin can update signals"
  on public.timeline_signals
  for update
  to authenticated
  using (lower(coalesce(auth.jwt() ->> 'email', '')) = 'anoopviswanathan@outlook.com')
  with check (lower(coalesce(auth.jwt() ->> 'email', '')) = 'anoopviswanathan@outlook.com');

drop policy if exists "Timeline admin can delete signals" on public.timeline_signals;
create policy "Timeline admin can delete signals"
  on public.timeline_signals
  for delete
  to authenticated
  using (lower(coalesce(auth.jwt() ->> 'email', '')) = 'anoopviswanathan@outlook.com');
