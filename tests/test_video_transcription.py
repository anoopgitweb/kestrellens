import io
import json
import unittest
import urllib.error
from unittest.mock import patch
import video_transcription as vt

USER = '11111111-1111-4111-8111-111111111111'
PATH = USER+'/22222222-2222-4222-8222-222222222222/33333333-3333-4333-8333-333333333333.mp4'


class VideoTranscriptionTests(unittest.TestCase):
    def setUp(self):
        vt.JOBS.clear()

    def test_rejects_foreign_and_malformed_paths(self):
        for path in [PATH.replace(USER, '44444444-4444-4444-8444-444444444444'), '../video.mp4', PATH+'?url=http://bad']:
            with self.assertRaises((ValueError, PermissionError)):
                vt.validate_path(path, USER)

    def test_cache_does_not_start_paid_work(self):
        with patch.object(vt, 'storage', return_value=b'{"text":"Saved","segments":[]}'), patch.object(vt.POOL, 'submit') as submit:
            result = vt.request_transcript({'path':PATH,'action':'start'}, USER, 'token', 'url', 'key', '')
            self.assertEqual(result['transcript']['text'], 'Saved')
            submit.assert_not_called()

    def test_start_deduplicates_and_status_is_scoped(self):
        missing = urllib.error.HTTPError('url', 404, 'missing', {}, io.BytesIO())
        with patch.object(vt, 'storage', side_effect=missing), patch.object(vt.POOL, 'submit') as submit:
            args = ({'path':PATH,'action':'start'}, USER, 'token', 'url', 'key', 'api-key')
            first = vt.request_transcript(*args)
            second = vt.request_transcript(*args)
            self.assertEqual(first['job_id'], second['job_id'])
            self.assertEqual(submit.call_count, 1)
            job = vt.JOBS[first['job_id']]
            job['user_id'] = 'different'
            with self.assertRaises(ValueError):
                vt.request_transcript({'path':PATH,'job_id':first['job_id']}, USER, 'token', 'url', 'key', 'api-key')

    def test_storage_denial_does_not_start_work(self):
        with patch.object(vt, 'storage', side_effect=urllib.error.HTTPError('url',403,'denied',{},None)), patch.object(vt.POOL,'submit') as submit:
            with self.assertRaises(urllib.error.HTTPError):
                vt.request_transcript({'path':PATH,'action':'start'},USER,'token','url','key','api-key')
            submit.assert_not_called()

    def test_audio_request_uses_timestamps_and_bounded_model(self):
        with patch.object(vt.urllib.request,'urlopen',return_value=io.BytesIO(b'{"text":"Hello","segments":[]}')) as request:
            vt.transcribe_audio(b'audio','secret')
            req=request.call_args.args[0]
            self.assertEqual(req.full_url,'https://api.openai.com/v1/audio/transcriptions')
            self.assertIn(b'verbose_json',req.data)
            self.assertIn(b'timestamp_granularities[]',req.data)

    def test_real_audio_extraction_and_transcript_save(self):
        import imageio_ffmpeg
        import subprocess
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'sample.mp4'
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i',
                'sine=frequency=400:duration=1', '-c:a', 'aac', str(source)], check=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            vt.JOBS['sample'] = {'status':'processing'}
            with patch.object(vt,'storage',side_effect=[source.read_bytes(),b'{}']) as storage, patch.object(vt,'transcribe_audio',return_value={'text':'Hello','segments':[{'start':0,'end':1,'text':'Hello'}]}):
                vt.run_job('sample','url','key','token',PATH,'api-key')
            self.assertEqual(vt.JOBS['sample']['status'],'complete')
            self.assertEqual(storage.call_args.args[3],PATH+'.transcript.json')
            self.assertEqual(json.loads(storage.call_args.args[4])['text'],'Hello')


if __name__ == '__main__':
    unittest.main()
