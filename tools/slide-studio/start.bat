@echo off
cd /d "%~dp0"
if exist "C:\Users\manju\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "C:\Users\manju\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" run.py
) else (
  py run.py
)
pause
