"""Serve the offline editor on an OS-assigned local port for KestrelIQ."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / '.packages'))
from app import app
from werkzeug.serving import make_server

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = make_server('127.0.0.1', args.port, app, threaded=True)
    print(f'Slide Studio is ready at http://127.0.0.1:{server.server_port}', flush=True)
    server.serve_forever()
