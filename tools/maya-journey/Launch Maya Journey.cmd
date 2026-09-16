@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Maya Journey is not installed yet.
  echo Open README.md and follow the one-time installation steps.
  pause
  exit /b 1
)
start "Maya Journey Server" /min ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000"
endlocal
