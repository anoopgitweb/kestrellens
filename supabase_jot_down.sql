-- KestrelIQ Discover & Learn / Jot Down
-- Run this entire script once in the Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.note_topics (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(title) between 1 and 120),
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.note_subtopics (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  topic_id uuid not null references public.note_topics(id) on delete cascade,
  title text not null check (char_length(title) between 1 and 160),
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  subtopic_id uuid not null unique references public.note_subtopics(id) on delete cascade,
  title text not null default 'Untitled note' check (char_length(title) between 1 and 200),
  content text not null default '' check (char_length(content) <= 500000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists note_topics_user_order_idx
  on public.note_topics(user_id, sort_order, created_at);
create index if not exists note_subtopics_user_topic_order_idx
  on public.note_subtopics(user_id, topic_id, sort_order, created_at);
create index if not exists notes_user_subtopic_idx
  on public.notes(user_id, subtopic_id);

alter table public.note_topics enable row level security;
alter table public.note_subtopics enable row level security;
alter table public.notes enable row level security;

drop policy if exists "Users manage their note topics" on public.note_topics;
create policy "Users manage their note topics"
  on public.note_topics
  for all
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "Users manage their note subtopics" on public.note_subtopics;
create policy "Users manage their note subtopics"
  on public.note_subtopics
  for all
  to authenticated
  using (
    auth.uid() = user_id
    and exists (
      select 1
      from public.note_topics topic
      where topic.id = topic_id
        and topic.user_id = auth.uid()
    )
  )
  with check (
    auth.uid() = user_id
    and exists (
      select 1
      from public.note_topics topic
      where topic.id = topic_id
        and topic.user_id = auth.uid()
    )
  );

drop policy if exists "Users manage their notes" on public.notes;
create policy "Users manage their notes"
  on public.notes
  for all
  to authenticated
  using (
    auth.uid() = user_id
    and exists (
      select 1
      from public.note_subtopics subtopic
      where subtopic.id = subtopic_id
        and subtopic.user_id = auth.uid()
    )
  )
  with check (
    auth.uid() = user_id
    and exists (
      select 1
      from public.note_subtopics subtopic
      where subtopic.id = subtopic_id
        and subtopic.user_id = auth.uid()
    )
  );

grant select, insert, update, delete on public.note_topics to authenticated;
grant select, insert, update, delete on public.note_subtopics to authenticated;
grant select, insert, update, delete on public.notes to authenticated;

-- Private, user-scoped storage for pasted images and optional page attachments.
-- Images are compressed to WebP; documents are limited to 5 MB by the bucket.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'jot-down-images',
  'jot-down-images',
  false,
  5242880,
  array[
    'image/webp',
    'image/jpeg',
    'image/png',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv',
    'text/plain'
  ]
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Users read their Jot Down images" on storage.objects;
create policy "Users read their Jot Down images"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'jot-down-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "Users upload their Jot Down images" on storage.objects;
create policy "Users upload their Jot Down images"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'jot-down-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "Users update their Jot Down images" on storage.objects;
create policy "Users update their Jot Down images"
  on storage.objects for update to authenticated
  using (
    bucket_id = 'jot-down-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'jot-down-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "Users delete their Jot Down images" on storage.objects;
create policy "Users delete their Jot Down images"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'jot-down-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
