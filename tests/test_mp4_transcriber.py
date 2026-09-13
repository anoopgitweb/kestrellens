import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, r'C:\KestrelIQ')
import app
import mp4_transcriber as mp4


class Mp4TranscriberTests(unittest.TestCase):
    def tearDown(self):
        for job in mp4.JOBS.values():
            import shutil
            shutil.rmtree(job.get('folder'), ignore_errors=True)
        mp4.JOBS.clear()

    def sample(self, folder):
        path = Path(folder) / 'sample.mp4'
        subprocess.run([mp4._ffmpeg(), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:d=1',
                        '-f', 'lavfi', '-i', 'sine=duration=1', '-shortest', str(path)], check=True)
        return path

    def test_rejects_non_mp4_and_large_upload(self):
        with self.assertRaises(ValueError):
            mp4.start_upload(io.BytesIO(b'not video'), 9, 'owner')
        with self.assertRaises(ValueError):
            mp4.start_upload(io.BytesIO(), mp4.MAX_BYTES + 1, 'owner')

    def test_real_mp4_generates_three_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.sample(folder).read_bytes()
        segment = SimpleNamespace(start=0, end=1, text=' Hello MP4 ')
        model = SimpleNamespace(transcribe=lambda *args, **kwargs: (iter([segment]), SimpleNamespace()))
        with patch.object(mp4, '_model', return_value=model), patch.object(mp4.POOL, 'submit', side_effect=lambda fn, *args: fn(*args)):
            result = mp4.start_upload(io.BytesIO(data), len(data), 'owner', 'tiny')
        job = mp4.status(result['job_id'], 'owner')
        self.assertEqual(job['status'], 'complete')
        self.assertEqual(job['segments'][0]['text'], 'Hello MP4')
        for name in ('transcript.txt', 'transcript.srt', 'transcript.vtt'):
            self.assertTrue(mp4.artifact(result['job_id'], 'owner', name).is_file())
        with self.assertRaises(ValueError):
            mp4.status(result['job_id'], 'another-user')

    def test_authenticated_routes_and_tool_page(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://localhost:' + str(server.server_port)
        token = app._tool_launch_token('owner', 'mp4-transcriber', int(time.time()) + 600)
        try:
            with urllib.request.urlopen(base + '/tools/mp4-transcriber?launch=' + token) as response:
                self.assertIn(b'MP4 Transcriber', response.read())
            payload = json.dumps({'action': 'dependencies', 'launch': token}).encode()
            request = urllib.request.Request(base + '/api/mp4-transcriber', data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                self.assertIn('faster_whisper', json.load(response))
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base + '/tools/mp4-transcriber')
            self.assertEqual(error.exception.code, 401)
            self.assertEqual(app.INDEX_FILE.read_text(encoding='utf-8').count("openToolKitPage('/tools/mp4-transcriber')"), 2)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
