"""On-demand, loopback-only Slide Studio process for the local KestrelIQ toolkit."""
import atexit
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

_lock = threading.Lock()
_process = None
_url = None


def stop():
    global _process, _url
    with _lock:
        if _process is not None and _process.poll() is None:
            _process.terminate()
            try:
                _process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _process.kill()
                _process.wait(timeout=5)
        _process = None
        _url = None


atexit.register(stop)


def launch(root):
    global _process, _url
    with _lock:
        if _process is not None and _process.poll() is None:
            return _url
        tool = Path(root) / 'tools' / 'slide-studio'
        runtime = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies'
        local = tool / '.venv/Scripts/python.exe'
        bundled = runtime / 'python/python.exe'
        python = str(local if local.exists() else bundled if bundled.exists() else sys.executable)
        env = os.environ.copy()
        # Port zero lets the OS reserve an unused port atomically.
        child = subprocess.Popen(
            [python, '-u', str(tool / 'kestrel_run.py'), '--port', '0'],
            cwd=tool, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        ready = queue.Queue()
        def read_output():
            for line in child.stdout:
                if line.startswith('Slide Studio is ready at http://127.0.0.1:'):
                    ready.put(line.split(' at ', 1)[1].split()[0])
            ready.put(None)
        threading.Thread(target=read_output, daemon=True).start()
        try:
            url = ready.get(timeout=30)
            if not url:
                raise RuntimeError('Slide Studio could not start. Check its Python dependencies in tools/slide-studio/README.md.')
        except (queue.Empty, RuntimeError) as exc:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
            raise RuntimeError('Slide Studio could not start. Check its Python dependencies in tools/slide-studio/README.md.') from exc
        _process, _url = child, url
        return url
