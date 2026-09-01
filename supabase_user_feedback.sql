-- Run once in the Supabase SQL editor for the KestrelIQ project.
create table if not exists public.user_feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  user_email text not null default '',
  category text not null default 'general',
  rating smallint,
  message text not null,
  page_context text not null default '',
  status text not null default 'new',
  created_at timestamptz not null default now(),
  constraint user_feedback_rating_check check (rating is null or rating between 1 and 5),
  constraint user_feedback_category_check check (category in ('general','idea','issue','learning','content'))
);

create index if not exists user_feedback_created_at_idx
  on public.user_feedback (created_at desc);
create index if not exists user_feedback_user_id_idx
  on public.user_feedback (user_id);

alter table public.user_feedback enable row level security;

drop policy if exists "Users can submit feedback" on public.user_feedback;
create policy "Users can submit feedback"
  on public.user_feedback for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users can read their feedback" on public.user_feedback;
create policy "Users can read their feedback"
  on public.user_feedback for select
  using (auth.uid() = user_id);

-- The admin list is read by the KestrelIQ backend with the Supabase service-role key.
