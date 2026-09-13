# Discover & Learn video transcripts

## Enable

1. Run `supabase_video_transcripts.sql` in the existing Supabase project's SQL Editor. For a new notebook installation, `supabase_jot_down.sql` includes the same media types and size limit.
2. Deploy the updated application and install `requirements.txt` (includes the FFmpeg runtime).
3. Set `OPENAI_API_KEY` on the server. It never goes to the browser. Existing Supabase URL and anon-key settings are used, with the signed-in user's token for private storage access.

## Use

Create or edit a Discover & Learn page, select **Upload videos**, and save. Open its **Video** button or video attachment, then select **Transcribe video**. The original video stays in private storage; only extracted audio is sent to OpenAI. YouTube links are not transcribed.

Supports MP4, WebM and MOV up to 100 MB / 30 minutes each. Playback depends on browser codec support. The backend extracts mono audio and transcribes it in ten-minute chunks using `whisper-1`, retaining segment timestamps.

Transcripts are private JSON objects in the `jot-down-images` bucket beside the video: `<owner>/<chapter>/<video>.mp4.transcript.json`. No new database table is required. Generating/loading through the transcription API is scoped to the uploading account. Existing storage policies remain unchanged.

The viewer offers TXT and SRT downloads, plus **Print / Save PDF** using the browser print dialog. Clicking a transcript segment seeks the video to its timestamp. Previously saved transcripts load without another paid transcription call.

Processing has two concurrent slots per server and a six-job hourly limit per user. Keep the tab open to see progress; jobs continue if the viewer closes, but an application restart cancels in-progress jobs. Reopen and retry after a restart; completed transcripts remain saved. For multi-worker hosting or large-scale use, replace the in-process worker queue with a shared durable queue.

## Checks

`python -m unittest discover -s tests -p test_video_transcription.py`

`node tests/learning-video.test.cjs` (requires Playwright and Edge, or `KESTREL_TEST_BROWSER`)

Tests mock paid transcription and Supabase calls. A real uploaded-video transcription must be checked after configuring the deployment.
