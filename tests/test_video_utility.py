import sys
sys.path.insert(0, r'C:\KestrelIQ')
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import video_utility as v
import app

class UtilityTests(unittest.TestCase):
    def test_urls(self):
        for value in ['https://youtu.be/abcdefghijk', 'https://www.youtube.com/shorts/abcdefghijk']:
            self.assertEqual(v.youtube_url(value), 'https://www.youtube.com/watch?v=abcdefghijk')
        for value in ['http://localhost/x', 'https://youtube.com.evil/watch?v=abcdefghijk', 'https://youtube.com/playlist?list=x', 'https://youtu.be/short']:
            with self.assertRaises(ValueError): v.youtube_url(value)

    def test_exports(self):
        segments = [{'start': 59.9996, 'end': 3601.02, 'text': 'Hello world'}]
        self.assertIn('00:01:00,000 --> 01:00:01,020', v.export(segments, 'srt'))
        self.assertTrue(v.export(segments, 'vtt').startswith('WEBVTT\n'))
        self.assertEqual(v.export(segments, 'txt'), 'Hello world\n')

    def test_permission_and_ownership(self):
        with self.assertRaises(ValueError): v.request({'action':'start','url':'https://youtu.be/abcdefghijk'}, 'one')
        with self.assertRaises(ValueError): v.artifact('missing','one','../secret')
        v.JOBS['private'] = {'owner':'one'}
        try:
            with self.assertRaises(ValueError): v.request({'action':'status','job_id':'private'}, 'two')
        finally: del v.JOBS['private']

    def test_real_conversion_mock_download_and_speech(self):
        import subprocess
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            subprocess.run([v.ffmpeg(), '-v','error','-f','lavfi','-i','sine=frequency=400:duration=1','-c:a','aac',str(folder/'source.m4a')],check=True)
            v.JOBS['sample'] = {'folder':folder,'owner':'one','status':'processing'}
            try:
                with patch.object(v,'metadata',return_value={'title':'Sample','duration':1}), patch('yt_dlp.YoutubeDL') as downloader, patch('faster_whisper.WhisperModel') as model:
                    model.return_value.transcribe.return_value = (iter([SimpleNamespace(start=0,end=1,text='Hello')]),None)
                    v.run('sample','https://youtu.be/abcdefghijk','audio-only',True,'tiny')
                self.assertEqual(v.JOBS['sample']['status'],'complete',v.JOBS['sample'])
                self.assertTrue((folder/'media.m4a').is_file())
                self.assertEqual((folder/'transcript.txt').read_text(),'Hello\n')
                self.assertTrue((folder/'transcript.vtt').is_file())
            finally: del v.JOBS['sample']

    def test_real_mp4_conversion(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            subprocess.run([v.ffmpeg(),'-v','error','-f','lavfi','-i','color=c=blue:s=320x240:d=1','-f','lavfi','-i','sine=duration=1','-shortest',str(folder/'source.mkv')],check=True)
            v.JOBS['movie']={'folder':folder,'owner':'one','status':'processing'}
            try:
                with patch.object(v,'metadata',return_value={'title':'Test','duration':1}),patch('yt_dlp.YoutubeDL'):
                    v.run('movie','https://youtu.be/abcdefghijk','480p',False,'tiny')
                self.assertEqual(v.JOBS['movie']['status'],'complete',v.JOBS['movie'])
                self.assertTrue((folder/'media.mp4').stat().st_size>0)
            finally: del v.JOBS['movie']

    def test_http_navigation_and_api(self):
        server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base = 'http://localhost:'+str(server.server_port)
        launch = app._tool_launch_token('test-user','video-utility',int(time.time())+600)
        try:
            with urllib.request.urlopen(base+'/tools/video-utility?launch='+launch) as r:
                self.assertIn(b'Video &amp; Transcript Utility',r.read())
            payload = json.dumps({'action':'dependencies','launch':launch}).encode()
            req=urllib.request.Request(base+'/api/video-utility',data=payload,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as r: self.assertIn('ffmpeg',json.load(r))
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base+'/tools/video-utility')
            self.assertEqual(error.exception.code,401)
            content=app.INDEX_FILE.read_text(encoding='utf-8')
            self.assertEqual(content.count("openToolKitPage('/tools/video-utility')"),2)
        finally: server.shutdown();server.server_close()

if __name__ == '__main__': unittest.main()
