# Video & Transcript Utility

Install locally with `python -m pip install -r requirements-video.txt`, then restart `python app.py`.
Use Python 3.11 or newer. FFmpeg is found on PATH or supplied by imageio-ffmpeg.
faster-whisper runs on CPU using int8. The first use of each model downloads its weights; subsequent runs use the local cache. No transcription API key is required.

Open Tool Kit > Productivity Tool Kit > Video & Transcript Utility. Administrators can enable `video-utility` in the existing account tool-access controls. This module accepts only local requests and uses the existing signed toolkit launch session (eight hours).

Confirm rights, validate a single YouTube video, select Best / 1080p / 720p / 480p / audio-only, and start. Resolution is an upper bound, never an upscale. FFmpeg converts video to H.264/AAC MP4; audio-only produces AAC M4A. Select local transcription to preview speech and export UTF-8 TXT, SRT or VTT. Speech recognition can make mistakes; review before sharing.

Only one job runs at a time. Videos must be published, at most two hours, and each downloaded stream is bounded to 2 GB. Temporary files are stored in the operating system temporary directory; finished jobs are expired after 24 hours when another job starts. Save outputs before restarting the application: job references are held in memory. Orphaned temporary folders from restarts can be removed manually when no job is running. Up to ten jobs are retained per application process.

Private/restricted videos, playlists and ongoing live streams are unsupported. YouTube extraction may require an updated yt-dlp or supported JavaScript runtime as YouTube changes. See the [yt-dlp documentation](https://github.com/yt-dlp/yt-dlp) and [faster-whisper documentation](https://github.com/SYSTRAN/faster-whisper) for installation troubleshooting. If transcription fails after conversion, the media download remains available. Existing Discover & Learn transcription continues to use its existing configuration.
