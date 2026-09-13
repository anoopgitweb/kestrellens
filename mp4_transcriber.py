"""Authenticated MP4 upload and server-side transcription jobs."""
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MAX_BYTES = 500 * 1024 * 1024
MAX_SECONDS = 2 * 60 * 60
POOL = ThreadPoolExecutor(max_workers=1)
LOCK = threading.RLock()
MODEL_LOCK = threading.Lock()
JOBS = {}
MODELS = {}


def _ffmpeg():
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise ValueError('FFmpeg is unavailable on the server.') from exc


def dependencies():
    try:
        _ffmpeg()
        ffmpeg_ready = True
    except ValueError:
        ffmpeg_ready = False
    try:
        import faster_whisper  # noqa: F401
        whisper_ready = True
    except ImportError:
        whisper_ready = False
    return {'ffmpeg': ffmpeg_ready, 'faster_whisper': whisper_ready}


def _timestamp(value, vtt=False):
    total, milliseconds = divmod(max(0, round(float(value) * 1000)), 1000)
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}{"." if vtt else ","}{milliseconds:03}'


def _export(segments, kind):
    if kind == 'txt':
        return '\n'.join(item['text'] for item in segments) + '\n'
    lines = ['WEBVTT', ''] if kind == 'vtt' else []
    for number, item in enumerate(segments, 1):
        lines.extend([str(number), f'{_timestamp(item["start"], kind == "vtt")} --> {_timestamp(item["end"], kind == "vtt")}', item['text'], ''])
    return '\n'.join(lines)


def _duration(path):
    process = subprocess.run([_ffmpeg(), '-hide_banner', '-i', str(path)], capture_output=True,
                             timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    output = process.stderr.decode('utf-8', errors='replace')
    match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', output)
    if not match:
        raise ValueError('The uploaded file is not a readable MP4 video.')
    return int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])


def _model(name):
    with MODEL_LOCK:
        if name not in MODELS:
            from faster_whisper import WhisperModel
            MODELS[name] = WhisperModel(name, device='cpu', compute_type='int8')
        return MODELS[name]


def _run(job_id, model_name):
    def update(**values):
        with LOCK:
            JOBS[job_id].update(values)
    job = JOBS[job_id]
    source = job['folder'] / 'source.mp4'
    try:
        update(message='Checking video')
        duration = _duration(source)
        if duration > MAX_SECONDS:
            raise ValueError('Choose an MP4 up to two hours long.')
        update(duration=duration, message='Loading speech model')
        stream, info = _model(model_name).transcribe(str(source), beam_size=5, vad_filter=True)
        segments = []
        for segment in stream:
            text = str(segment.text or '').strip()
            if text:
                segments.append({'start': round(float(segment.start), 3), 'end': round(float(segment.end), 3), 'text': text})
            update(message='Transcribing video', percent=min(99, round(float(segment.end) / duration * 100)))
        if not segments:
            raise ValueError('No speech was detected in this video.')
        for kind in ('txt', 'srt', 'vtt'):
            (job['folder'] / f'transcript.{kind}').write_text(_export(segments, kind), encoding='utf-8')
        source.unlink(missing_ok=True)
        update(status='complete', message='Transcript ready', percent=100, segments=segments)
    except Exception as exc:
        source.unlink(missing_ok=True)
        message = str(exc) if isinstance(exc, ValueError) else 'Transcription failed. Check the MP4 audio and server speech-model setup.'
        update(status='failed', message=message, percent=None)


def start_upload(stream, length, owner, model='base'):
    if model not in {'tiny', 'base', 'small'}:
        raise ValueError('Choose a supported speech model.')
    if length <= 0 or length > MAX_BYTES:
        raise ValueError('Choose an MP4 file up to 500 MB.')
    ready = dependencies()
    if not all(ready.values()):
        raise ValueError('The server is missing FFmpeg or faster-whisper.')
    with LOCK:
        _cleanup()
        if any(job['status'] == 'processing' for job in JOBS.values()):
            raise ValueError('Another MP4 is being transcribed. Please try again when it completes.')
        job_id = uuid.uuid4().hex
        folder = Path(tempfile.mkdtemp(prefix='kestreliq-mp4-'))
        JOBS[job_id] = {'job_id': job_id, 'owner': owner, 'folder': folder, 'created': time.time(),
                        'status': 'processing', 'message': 'Uploading MP4', 'percent': 0}
    source = folder / 'source.mp4'
    try:
        remaining = length
        with source.open('wb') as output:
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError('The upload ended before the complete MP4 was received.')
                output.write(chunk)
                remaining -= len(chunk)
        with source.open('rb') as uploaded:
            header = uploaded.read(64)
        if b'ftyp' not in header:
            raise ValueError('The selected file is not an MP4 video.')
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        with LOCK:
            JOBS.pop(job_id, None)
        raise
    POOL.submit(_run, job_id, model)
    return {'job_id': job_id, 'status': 'processing', 'message': 'MP4 uploaded'}


def _cleanup():
    for key, job in list(JOBS.items()):
        if job['status'] != 'processing' and time.time() - job['created'] > 24 * 3600:
            shutil.rmtree(job['folder'], ignore_errors=True)
            del JOBS[key]


def status(job_id, owner):
    with LOCK:
        job = JOBS.get(str(job_id or ''))
        if not job or job['owner'] != owner:
            raise ValueError('Transcription job expired or unavailable.')
        return {key: value for key, value in job.items() if key not in {'owner', 'folder', 'created'}}


def artifact(job_id, owner, name):
    if name not in {'transcript.txt', 'transcript.srt', 'transcript.vtt'}:
        raise ValueError('Transcript file unavailable.')
    with LOCK:
        job = JOBS.get(str(job_id or ''))
        if not job or job['owner'] != owner or job['status'] != 'complete':
            raise ValueError('Transcript file unavailable.')
        path = job['folder'] / name
        if not path.is_file():
            raise ValueError('Transcript file unavailable.')
        return path
