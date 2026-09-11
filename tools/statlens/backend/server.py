"""Loopback-only offline server. Run: python backend/server.py."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.runtime'))
sys.path.insert(0, str(ROOT))
import argparse
import csv
import io
import json
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import pandas as pd
from backend.engine import analyze, clean

MAX_BYTES = 100 * 1024 * 1024
JOBS = {}
LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=1)
TTL = 3600


def read_dataset(data, filename):
    ext = Path(filename).suffix.lower()
    if ext in ('.csv', '.tsv'):
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ValueError('Save the file as UTF-8 CSV or upload an XLSX workbook.')
        delimiter = '\t' if ext == '.tsv' else ','
        header = next(csv.reader(io.StringIO(text), delimiter=delimiter), [])
        if not header or any(not h.strip() for h in header) or len(set(header)) != len(header):
            raise ValueError('Every column needs a non-empty, unique header.')
        df = pd.read_csv(io.StringIO(text), sep=delimiter, low_memory=False)
    elif ext == '.xlsx':
        import zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 500*1024*1024:
                raise ValueError('Expanded workbook exceeds the 500 MB limit. Use CSV instead.')
        raw = pd.read_excel(io.BytesIO(data), sheet_name=0, header=None)
        if raw.empty:
            raise ValueError('The first worksheet is empty.')
        header = raw.iloc[0]
        if header.isna().any() or header.astype(str).duplicated().any():
            raise ValueError('Every column needs a non-empty, unique header.')
        df = raw.iloc[1:].reset_index(drop=True)
        df.columns = header.astype(str)
    else:
        raise ValueError('Supported files: CSV, TSV and XLSX (first worksheet).')
    if df.empty:
        raise ValueError('The dataset has no data rows.')
    if len(df.columns) > 300:
        raise ValueError('The current version supports up to 300 columns.')
    df.columns = df.columns.astype(str)
    return df


def run_job(key, data=None, filename=None, overrides=None):
    def progress(percent, message):
        with LOCK:
            JOBS[key].update(progress=percent, message=message)
    try:
        with LOCK:
            job = JOBS[key]
        frame = read_dataset(data, filename) if data is not None else job['frame']
        with LOCK:
            job['frame'] = frame
        result = analyze(frame, job['filename'], overrides, progress)
        with LOCK:
            job.update(status='done', progress=100, message='Analysis complete', result=result)
    except Exception as exc:
        with LOCK:
            JOBS[key].update(status='error', message=f'Analysis could not complete: {exc}')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send(self, status, body, content_type='application/json; charset=utf-8', attachment=None):
        if not isinstance(body, bytes):
            body = json.dumps(clean(body), allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        if attachment:
            self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in hosts:
            self.send(403, {'error':'Invalid local host.'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://' + h for h in hosts}:
            self.send(403, {'error':'Cross-origin requests are disabled.'})
            return False
        return True

    def get_job(self, key):
        with LOCK:
            job = JOBS.get(key)
            if job:
                job['access'] = time.time()
            return job

    def do_GET(self):
        if not self.allowed():
            return
        url = urlparse(self.path)
        if url.path == '/api/health':
            return self.send(200, {'status':'ok'})
        if url.path.startswith('/api/jobs/'):
            parts = url.path.strip('/').split('/')
            job = self.get_job(parts[2])
            if not job:
                return self.send(404, {'error':'Dataset session expired. Upload again.'})
            if len(parts) == 4 and parts[3] == 'export':
                if job['status'] != 'done':
                    return self.send(409, {'error':'Analysis is not complete.'})
                result = job['result']
                kind = parse_qs(url.query).get('format',['json'])[0]
                if kind == 'csv':
                    output = io.StringIO(newline='')
                    writer = csv.writer(output)
                    writer.writerow(['Module','Analysis','Explanation','Metrics','Method','Caveat','p','Adjusted q'])
                    for r in result['results']:
                        cells = [r['module'],r['title'],r['explanation'],json.dumps(r['metrics']),r['method'],r['caveat'],r.get('p_value',''),r.get('q_value','')]
                        writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in cells])
                    return self.send(200, output.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8', 'analysis-results.csv')
                return self.send(200, result, attachment='analysis-report.json')
            payload = {k:job[k] for k in ('status','progress','message')}
            if job['status'] == 'done':
                payload['result'] = job['result']
            return self.send(200, payload)
        files = {'/':('index.html','text/html'), '/app.js':('app.js','text/javascript'), '/style.css':('style.css','text/css'), '/extra.css':('extra.css','text/css')}
        if url.path in files:
            file, mime = files[url.path]
            return self.send(200, (ROOT/'frontend'/file).read_bytes(), mime+'; charset=utf-8')
        self.send(404, {'error':'Not found.'})

    def do_POST(self):
        if not self.allowed():
            return
        if self.headers.get('X-Local-App') != 'statlens':
            return self.send(403, {'error':'Use the local application to upload data.'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= MAX_BYTES:
                return self.send(413, {'error':'Upload a non-empty file of up to 100 MB.'})
            data = self.rfile.read(size)
            url = urlparse(self.path)
            if url.path == '/api/upload':
                filename = parse_qs(url.query).get('filename',['dataset.csv'])[0]
                with LOCK:
                    for k in list(JOBS):
                        if JOBS[k]['status'] != 'running' and time.time()-JOBS[k]['access'] > TTL:
                            del JOBS[k]
                    if any(j['status']=='running' for j in JOBS.values()):
                        return self.send(409, {'error':'An analysis is already running. Wait for it to finish.'})
                    while len(JOBS) >= 3:
                        del JOBS[min(JOBS, key=lambda k:JOBS[k]['access'])]
                    key = uuid.uuid4().hex
                    JOBS[key] = dict(filename=filename, status='running', progress=2, message='Reading the dataset', access=time.time())
                POOL.submit(run_job, key, data, filename)
                return self.send(202, {'id':key})
            if url.path.startswith('/api/reanalyze/'):
                key = url.path.rsplit('/',1)[-1]
                job = self.get_job(key)
                if not job or 'frame' not in job:
                    return self.send(404, {'error':'Dataset session expired. Upload again.'})
                overrides = json.loads(data)
                valid = {'numeric','categorical','date','id','text','boolean','constant','empty'}
                if not isinstance(overrides,dict) or any(k not in job['frame'].columns or v not in valid for k,v in overrides.items()):
                    raise ValueError('Invalid column type selection.')
                with LOCK:
                    if any(j['status']=='running' for j in JOBS.values()):
                        return self.send(409, {'error':'An analysis is already running.'})
                    job.update(status='running', progress=2, message='Applying column types')
                POOL.submit(run_job, key, overrides=overrides)
                return self.send(202, {'id':key})
            if url.path.startswith('/api/jobs/') and url.path.endswith('/ppt'):
                key = url.path.strip('/').split('/')[2]
                job = self.get_job(key)
                if not job or job.get('status') != 'done':
                    return self.send(409, {'error':'Complete the analysis before generating a presentation.'})
                request = json.loads(data)
                ids = request.get('result_ids', []) if isinstance(request, dict) else []
                by_id = {r['id']: r for r in job['result']['results']}
                if not isinstance(ids, list) or not ids or len(ids) > 80 or any(i not in by_id for i in ids):
                    return self.send(400, {'error':'Select between one and 80 completed analyses.'})
                build = ROOT / '.ppt-build'
                output_dir = ROOT / '.ppt-output'
                build.mkdir(exist_ok=True)
                output_dir.mkdir(exist_ok=True)
                output = output_dir / f'statlens-{uuid.uuid4().hex}.pptx'
                payload = {'filename':job['filename'], 'selectedCount':len(ids), 'results':[by_id[i] for i in ids]}
                node = os.environ.get('STATLENS_NODE') or r'C:\Users\manju\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
                generator = ROOT / 'backend' / 'ppt_generator.mjs'
                generated = subprocess.run([node, str(generator), str(output)], input=json.dumps(payload), text=True, capture_output=True, timeout=180)
                if generated.returncode != 0 or not output.exists():
                    return self.send(500, {'error':'PowerPoint generation failed. '+(generated.stderr[-500:] or 'Try fewer analyses.')})
                body = output.read_bytes()
                try: output.unlink()
                except OSError: pass
                return self.send(200, body, 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'statlens-analysis.pptx')
            self.send(404, {'error':'Not found.'})
        except (ValueError, json.JSONDecodeError) as exc:
            self.send(400, {'error':str(exc)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1',args.port), Handler)
    print(f'StatLens is ready at http://127.0.0.1:{server.server_port} — Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == '__main__':
    main()
