"""Video processing on the KestrelIQ server, isolated from notebook transcription."""
import importlib.util
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

POOL = ThreadPoolExecutor(max_workers=1)
LOCK = threading.RLock()
JOBS = {}
QUALITIES = {'Best', '1080p', '720p', '480p', 'audio-only'}

def javascript_runtimes():
    runtimes = {name: {} for name in ('deno', 'node', 'bun', 'quickjs') if shutil.which(name)}
    try:
        import deno
        bundled = str(deno.find_deno_bin())
        if Path(bundled).is_file():
            runtimes['deno'] = {'path': bundled}
    except (ImportError, OSError, RuntimeError):
        pass
    return runtimes

def youtube_options(**extra):
    runtimes = javascript_runtimes()
    return {'quiet': True, 'no_warnings': True, 'noplaylist': True, 'socket_timeout': 30,
            'retries': 2, 'js_runtimes': runtimes, 'remote_components': ['ejs:github'],
            'extractor_args': {'youtube': {'player_client': ['default', 'tv', 'web_embedded']}}, **extra}

def youtube_failure(exc):
    message = re.sub(r'\x1b\[[0-9;]*m', '', str(exc))
    lowered = message.lower()
    if 'sign in to confirm' in lowered or 'not a bot' in lowered:
        return 'YouTube blocked this hosting server from accessing the video. Try another public video or process it locally.'
    if 'private video' in lowered or 'members-only' in lowered:
        return 'This video is private or members-only and cannot be processed.'
    if 'age' in lowered and ('restrict' in lowered or 'confirm' in lowered):
        return 'This video is age-restricted and cannot be processed without a YouTube sign-in.'
    if 'javascript runtime' in lowered or 'challenge' in lowered or 'signature' in lowered:
        return 'The server needs a supported JavaScript runtime for this YouTube video. Check the hosting build and redeploy.'
    if 'requested format' in lowered:
        return 'The selected quality is unavailable. Try Best or a lower resolution.'
    if 'video unavailable' in lowered or 'not available' in lowered:
        return 'This video is unavailable to the hosting server. It may be restricted, removed, or region-blocked.'
    if 'timed out' in lowered or 'temporary failure' in lowered:
        return 'YouTube did not respond in time. Please retry shortly.'
    detail = re.sub(r'https?://\S+', '[video URL]', message)
    detail = re.sub(r'(?i)\b(cookie|token|authorization|password)\s*[:=]\s*\S+', r'\1=[redacted]', detail)
    detail = re.sub(r'\s+', ' ', detail).strip()
    if detail.lower().startswith('error:'):
        detail = detail[6:].strip()
    return 'YouTube could not provide this video. Technical detail: ' + detail[:350]

def youtube_url(value):
    p = urlsplit(str(value or '').strip())
    if p.scheme not in {'https', 'http'} or p.username or p.password or p.port:
        raise ValueError('Enter a YouTube video URL.')
    if p.hostname in {'youtu.be', 'www.youtu.be'}:
        video = p.path.strip('/')
    elif p.hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
        parts = p.path.strip('/').split('/')
        video = (parse_qs(p.query).get('v') or [''])[0] if p.path == '/watch' else parts[1] if len(parts) == 2 and parts[0] in {'shorts', 'live', 'embed'} else ''
    else:
        video = ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
        raise ValueError('Enter a single YouTube watch, Shorts, Live or youtu.be video link.')
    return 'https://www.youtube.com/watch?v=' + video

def ffmpeg():
    found = shutil.which('ffmpeg')
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        raise ValueError('FFmpeg is missing. Install the video utility requirements and restart KestrelIQ.')

def dependencies():
    try:
        ffmpeg()
        ready = True
    except ValueError:
        ready = False
    return {'yt_dlp': bool(importlib.util.find_spec('yt_dlp')), 'javascript': bool(javascript_runtimes()), 'ffmpeg': ready,
            'faster_whisper': bool(importlib.util.find_spec('faster_whisper'))}

def metadata(url):
    try:
        import yt_dlp
    except ImportError:
        raise ValueError('yt-dlp is missing. Install requirements-video.txt and restart KestrelIQ.')
    try:
        with yt_dlp.YoutubeDL(youtube_options()) as downloader:
            info = downloader.extract_info(youtube_url(url), download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise ValueError(youtube_failure(exc)) from exc
    if not info or info.get('_type') == 'playlist' or info.get('is_live') or info.get('live_status') == 'is_upcoming':
        raise ValueError('Choose a published video; playlists and ongoing live streams are unsupported.')
    if not info.get('duration') or info['duration'] > 7200:
        raise ValueError('Choose a video up to two hours long.')
    return {key: info.get(key) for key in ('id', 'title', 'uploader', 'duration')} | {
        'heights': sorted({int(f['height']) for f in info.get('formats', []) if f.get('height')})}

def timestamp(seconds, vtt=False):
    millis = max(0, round(float(seconds) * 1000))
    seconds, ms = divmod(millis, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f'{hours:02}:{minute:02}:{sec:02}{"." if vtt else ","}{ms:03}'

def export(segments, kind):
    if kind == 'txt':
        return '\n'.join(s['text'] for s in segments) + '\n'
    if kind not in {'srt', 'vtt'}:
        raise ValueError('Unknown transcript format.')
    lines = ['WEBVTT\n'] if kind == 'vtt' else []
    for i, s in enumerate(segments, 1):
        lines.extend([str(i), f'{timestamp(s["start"], kind == "vtt")} --> {timestamp(s["end"], kind == "vtt")}', s['text'], ''])
    return '\n'.join(lines) + '\n'

def run(job_id, url, quality, transcribe, model):
    def update(**values):
        with LOCK:
            JOBS[job_id].update(values)
    folder = JOBS[job_id]['folder']
    try:
        import yt_dlp
        executable = ffmpeg()
        update(message='Validating video')
        info = metadata(url)
        update(metadata=info, message='Downloading media')
        cap = '' if quality == 'Best' else f'[height<={quality[:-1]}]'
        fmt = 'bestaudio/best' if quality == 'audio-only' else f'bestvideo{cap}+bestaudio/best{cap}'
        def progress(data):
            if data.get('status') == 'downloading':
                total = data.get('total_bytes') or data.get('total_bytes_estimate')
                if data.get('downloaded_bytes', 0) > 2 * 1024**3:
                    raise ValueError('This download exceeds the 2 GB limit.')
                update(message='Downloading media', percent=round(100 * data.get('downloaded_bytes', 0) / total) if total else None)
        options = youtube_options(format=fmt, outtmpl=str(folder / 'source.%(ext)s'),
                                  ffmpeg_location=executable, merge_output_format='mkv',
                                  max_filesize=2 * 1024**3, progress_hooks=[progress])
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                downloader.download([url])
        except yt_dlp.utils.DownloadError as exc:
            raise ValueError(youtube_failure(exc)) from exc
        sources = [p for p in folder.glob('source.*') if p.suffix not in {'.part', '.ytdl'}]
        if len(sources) != 1:
            raise ValueError('The download was incomplete or too large. Try a lower quality.')
        target = folder / ('media.m4a' if quality == 'audio-only' else 'media.mp4')
        update(message='Preparing audio file' if quality == 'audio-only' else 'Preparing MP4', percent=None)
        args = ['-vn', '-c:a', 'aac'] if quality == 'audio-only' else ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-c:a', 'aac', '-movflags', '+faststart']
        process = subprocess.run([executable, '-nostdin', '-v', 'error', '-i', str(sources[0]), *args, str(target)], capture_output=True, timeout=7200, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if process.returncode or not target.exists():
            raise ValueError('FFmpeg could not convert this media. Try another quality.')
        update(media=target.name)
        sources[0].unlink()
        if transcribe:
            update(message='Loading speech model on the server (first use downloads the model)')
            from faster_whisper import WhisperModel
            engine = WhisperModel(model, device='cpu', compute_type='int8')
            stream, details = engine.transcribe(str(target), beam_size=5)
            segments = []
            for s in stream:
                segments.append({'start': s.start, 'end': s.end, 'text': s.text.strip()})
                update(message='Transcribing on the server', percent=min(99, round(s.end / info['duration'] * 100)))
            if not any(s['text'] for s in segments):
                raise ValueError('No speech was detected. Your media download is still available.')
            for kind in ('txt', 'srt', 'vtt'):
                (folder / ('transcript.' + kind)).write_text(export(segments, kind), encoding='utf-8')
            update(segments=segments)
        update(status='complete', message='Ready to download', percent=100)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else 'Processing failed. Check your connection, update yt-dlp, and confirm the video is publicly accessible. For transcription, verify faster-whisper is installed and the model can download.'
        update(status='failed', message=message, percent=None)

def request(payload, owner):
    action = payload.get('action')
    if action == 'dependencies':
        return dependencies()
    if action == 'status':
        with LOCK:
            job = JOBS.get(payload.get('job_id'))
            if not job or job['owner'] != owner:
                raise ValueError('Job expired or unavailable. Start again.')
            return {k: v for k, v in job.items() if k not in {'owner', 'folder', 'created'}}
    if payload.get('rights') is not True:
        raise ValueError('Confirm you own this video or have permission to download and transcribe it.')
    url = youtube_url(payload.get('url'))
    if action == 'validate':
        return metadata(url)
    if action != 'start':
        raise ValueError('Unknown action.')
    quality, model = payload.get('quality'), payload.get('model', 'base')
    if quality not in QUALITIES or model not in {'tiny', 'base', 'small'}:
        raise ValueError('Choose a supported quality and speech model.')
    deps = dependencies()
    if not deps['yt_dlp'] or not deps['javascript'] or not deps['ffmpeg'] or (payload.get('transcribe') and not deps['faster_whisper']):
        raise ValueError('Install requirements-video.txt, including Deno, then restart KestrelIQ. Transcription requires faster-whisper.')
    with LOCK:
        for key, job in list(JOBS.items()):
            if job['status'] != 'processing' and time.time() - job['created'] > 86400:
                shutil.rmtree(job['folder'], ignore_errors=True)
                del JOBS[key]
        if any(j['status'] == 'processing' for j in JOBS.values()):
            raise ValueError('Another video is processing. Try again when it completes.')
        if len(JOBS) >= 10:
            raise ValueError('Ten jobs are retained. Restart KestrelIQ after saving your downloads.')
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {'job_id': job_id, 'owner': owner, 'folder': Path(tempfile.mkdtemp(prefix='kestreliq-video-')), 'created': time.time(), 'status': 'processing', 'message': 'Preparing video'}
        POOL.submit(run, job_id, url, quality, bool(payload.get('transcribe')), model)
    return {'job_id': job_id, 'status': 'processing'}

def artifact(job_id, owner, name):
    with LOCK:
        job = JOBS.get(job_id)
        if not job or job['owner'] != owner or name not in {'media.mp4', 'media.m4a', 'transcript.txt', 'transcript.srt', 'transcript.vtt'}:
            raise ValueError('Download unavailable.')
        path = job['folder'] / name
        if not path.is_file() or (name.startswith('media.') and not job.get('media')):
            raise ValueError('This file is not ready.')
        return path
