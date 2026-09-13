"""Private notebook video transcription with bounded background processing."""
import json
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_SECONDS = 1800
POOL = ThreadPoolExecutor(max_workers=2)
LOCK = threading.Lock()
JOBS = {}


def validate_path(path, user_id):
    parts = str(path).split('/')
    if len(parts) != 3 or parts[0] != str(user_id):
        raise PermissionError('Transcribe a video uploaded by your account.')
    for value in parts[:2]:
        uuid.UUID(value)
    if not re.fullmatch(r'[a-fA-F0-9-]{36}\.(mp4|webm|mov)', parts[2]):
        raise ValueError('Choose an uploaded MP4, WebM or MOV video.')
    uuid.UUID(parts[2].rsplit('.', 1)[0])
    return str(path)


def storage(url, key, token, path, data=None):
    req = urllib.request.Request(url.rstrip('/')+'/storage/v1/object/jot-down-images/'+urllib.parse.quote(path, safe='/'),
        data=data, method='POST' if data is not None else 'GET',
        headers={'apikey': key, 'Authorization': 'Bearer '+token, 'Content-Type': 'application/json', 'x-upsert': 'true'})
    with urllib.request.urlopen(req, timeout=90) as response:
        body = response.read(MAX_VIDEO_BYTES+1)
    if len(body) > MAX_VIDEO_BYTES:
        raise ValueError('Video must be no larger than 100 MB.')
    return body


def transcribe_audio(audio, api_key):
    boundary = 'kestrel'+uuid.uuid4().hex
    body = bytearray()
    for key, value in [('model', 'whisper-1'), ('response_format', 'verbose_json'), ('timestamp_granularities[]', 'segment')]:
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
    body.extend(audio)
    body.extend(f'\r\n--{boundary}--\r\n'.encode())
    req = urllib.request.Request('https://api.openai.com/v1/audio/transcriptions', data=bytes(body),
        headers={'Authorization': 'Bearer '+api_key, 'Content-Type': 'multipart/form-data; boundary='+boundary})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def run_job(job_id, url, key, token, path, api_key):
    def update(**values):
        with LOCK:
            JOBS[job_id].update(values)
    try:
        import imageio_ffmpeg
        update(message='Downloading video')
        video = storage(url, key, token, path)
        with tempfile.TemporaryDirectory(prefix='kestrel-transcript-') as folder:
            source, audio = Path(folder)/('video.'+path.rsplit('.', 1)[1]), Path(folder)/'audio.wav'
            source.write_bytes(video)
            del video
            update(message='Extracting audio')
            process = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v', 'error',
                '-protocol_whitelist', 'file,pipe', '-i', str(source), '-vn', '-t', str(MAX_SECONDS+1),
                '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(audio)],
                capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if process.returncode:
                raise ValueError('No readable audio found. Try a video containing speech.')
            segments, texts = [], []
            with wave.open(str(audio), 'rb') as wav:
                duration = wav.getnframes()/wav.getframerate()
                if duration > MAX_SECONDS:
                    raise ValueError('Choose a video up to 30 minutes long.')
                chunk_seconds = 600
                import io
                for offset in range(0, max(1, int(duration)+1), chunk_seconds):
                    frames = wav.readframes(chunk_seconds*16000)
                    if not frames:
                        break
                    update(message=f'Transcribing audio ({offset//600+1}/{max(1, int((duration+599)//600))})')
                    buffer = io.BytesIO()
                    with wave.open(buffer, 'wb') as chunk:
                        chunk.setnchannels(1); chunk.setsampwidth(2); chunk.setframerate(16000); chunk.writeframes(frames)
                    result = transcribe_audio(buffer.getvalue(), api_key)
                    texts.append(result.get('text', ''))
                    segments.extend({'start': round(float(s['start'])+offset, 3), 'end': round(float(s['end'])+offset, 3), 'text': str(s['text']).strip()} for s in result.get('segments', []))
            transcript = {'text': '\n\n'.join(texts).strip(), 'segments': segments, 'video_path': path, 'created_at': time.time()}
            if not transcript['text']:
                raise ValueError('No speech was detected in this video.')
            update(message='Saving transcript')
            storage(url, key, token, path+'.transcript.json', json.dumps(transcript).encode())
            update(status='complete', message='Transcript saved', transcript=transcript)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else 'Transcription could not complete. Check the server transcription and storage configuration, then retry.'
        update(status='failed', message=message)


def request_transcript(payload, user_id, token, url, key, api_key):
    path = validate_path(payload.get('path'), user_id)
    if payload.get('job_id'):
        with LOCK:
            job = JOBS.get(str(payload['job_id']))
            if not job or job['user_id'] != user_id or job['path'] != path:
                raise ValueError('Transcription job expired. Reopen the video to load a saved transcript or retry.')
            return {k:v for k,v in job.items() if k not in {'user_id', 'path', 'created'}}
    try:
        transcript = json.loads(storage(url, key, token, path+'.transcript.json'))
        return {'status': 'complete', 'transcript': transcript, 'message': 'Saved transcript'}
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 404):
            raise
    if payload.get('action') != 'start':
        return {'status': 'missing'}
    if not api_key:
        raise ValueError('Transcription is not configured. Ask your administrator to set OPENAI_API_KEY.')
    with LOCK:
        for job_id in list(JOBS):
            if JOBS[job_id]['status'] != 'processing' and time.time()-JOBS[job_id]['created'] > 3600:
                del JOBS[job_id]
        for job in JOBS.values():
            if job['user_id'] == user_id and job['path'] == path and job['status'] == 'processing':
                return {'status': 'processing', 'job_id': job['job_id'], 'message': job['message']}
        if sum(j['status']=='processing' for j in JOBS.values()) >= 2:
            raise ValueError('Transcription is busy. Please try again shortly.')
        if sum(j['user_id']==user_id for j in JOBS.values()) >= 6:
            raise ValueError('Hourly transcription limit reached. Please try again later.')
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {'job_id':job_id,'user_id':user_id,'path':path,'created':time.time(),'status':'processing','message':'Preparing video'}
        POOL.submit(run_job, job_id, url, key, token, path, api_key)
    return {'status':'processing','job_id':job_id,'message':'Preparing video'}
