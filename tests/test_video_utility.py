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

    def test_youtube_errors_are_actionable(self):
        samples = {
            'Sign in to confirm you are not a bot': 'blocked this hosting server',
            'Private video': 'private or members-only',
            'No supported JavaScript runtime': 'JavaScript runtime',
            'Requested format is not available': 'selected quality',
        }
        for source, expected in samples.items():
            self.assertIn(expected, v.youtube_failure(Exception(source)))
        diagnostic = v.youtube_failure(Exception('ERROR: extractor failed for https://youtube.test/watch?v=secret'))
        self.assertIn('extractor failed', diagnostic)
        self.assertNotIn('youtube.test', diagnostic)

    def test_dependencies_report_javascript_runtime(self):
        with patch.object(v.shutil, 'which', side_effect=lambda name: '/bin/deno' if name == 'deno' else '/bin/ffmpeg' if name == 'ffmpeg' else None):
            status = v.dependencies()
        self.assertTrue(status['javascript'])
        self.assertTrue(status['ffmpeg'])

    def test_bundled_deno_path_is_given_to_ytdlp(self):
        options = v.youtube_options()
        self.assertIn('deno', options['js_runtimes'])
        self.assertTrue(options['js_runtimes']['deno'].get('path'))
        self.assertIn('tv', options['extractor_args']['youtube']['player_client'])

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

    def test_hosted_requests_keep_auth_and_file_ownership(self):
        import http.client
        server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        token = app._tool_launch_token('web-owner','video-utility',int(time.time())+600)
        other = app._tool_launch_token('other-user','video-utility',int(time.time())+600)
        def call(path, payload=None):
            conn = http.client.HTTPConnection('127.0.0.1',server.server_port)
            conn.request('POST' if payload is not None else 'GET', path,
                         json.dumps(payload) if payload is not None else None,
                         {'Host':'kestreliq.example','Content-Type':'application/json'})
            res=conn.getresponse(); result=(res.status,res.read());conn.close();return result
        try:
            self.assertEqual(call('/api/video-utility',{'action':'dependencies','launch':token})[0],200)
            for invalid in ['', 'forged', app._tool_launch_token('web-owner','video-utility',1), app._tool_launch_token('web-owner','statlens',int(time.time())+600)]:
                self.assertEqual(call('/api/video-utility',{'action':'dependencies','launch':invalid})[0],403)
            with patch.object(v,'metadata',return_value={'title':'Hosted sample','duration':60,'heights':[720]}):
                self.assertEqual(call('/api/video-utility',{'action':'validate','launch':token,'url':'https://youtu.be/abcdefghijk','rights':True})[0],200)
            with tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);(folder/'transcript.txt').write_text('Hosted transcript')
                v.JOBS['hosted']={'owner':'web-owner','folder':folder,'status':'complete','job_id':'hosted'}
                try:
                    url='/api/video-utility/file?job_id=hosted&name=transcript.txt&launch='
                    self.assertEqual(call(url+token),(200,b'Hosted transcript'))
                    self.assertEqual(call(url+other)[0],404)
                    self.assertEqual(call('/api/video-utility',{'action':'status','launch':other,'job_id':'hosted'})[0],400)
                finally: del v.JOBS['hosted']
        finally: server.shutdown();server.server_close()

if __name__ == '__main__': unittest.main()
