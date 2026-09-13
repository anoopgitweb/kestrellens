-- Run once in Supabase SQL Editor. Existing private storage policies remain in place.
-- Videos and their adjacent .transcript.json files inherit owner access.
update storage.buckets
set file_size_limit = 104857600,
    allowed_mime_types = array(select distinct mime from unnest(
      coalesce(allowed_mime_types, array[]::text[]) ||
      array['video/mp4','video/webm','video/quicktime','application/json']) as mime)
where id = 'jot-down-images';
