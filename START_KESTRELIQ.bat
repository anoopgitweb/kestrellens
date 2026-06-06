@echo off
cd /d "%~dp0"
echo Starting KestrelIQ...
start "" "http://127.0.0.1:8787"
python app.py
pause
