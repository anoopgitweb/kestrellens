-- KestrelIQ TalentEdge assessment results
-- Run this script once in the Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.talentedge_assessments (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  candidate_id text not null check (char_length(candidate_id) between 1 and 120),
  candidate_name text not null check (char_length(candidate_name) between 1 and 160),
  candidate_role text not null default '' check (char_length(candidate_role) <= 160),
  assessments jsonb not null default '{}'::jsonb,
  overall_score smallint check (overall_score between 0 and 100),
  completed_count smallint not null default 0 check (completed_count between 0 and 5),
  status text not null default 'in_progress' check (status in ('in_progress', 'completed', 'incomplete')),
  started_at timestamptz not null,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists talentedge_assessments_user_updated_idx
  on public.talentedge_assessments(user_id, updated_at desc);
create index if not exists talentedge_assessments_candidate_idx
  on public.talentedge_assessments(candidate_id, updated_at desc);

alter table public.talentedge_assessments enable row level security;

drop policy if exists "Users manage their TalentEdge assessments" on public.talentedge_assessments;
create policy "Users manage their TalentEdge assessments"
  on public.talentedge_assessments
  for all
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update on public.talentedge_assessments to authenticated;
