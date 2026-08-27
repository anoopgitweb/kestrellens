@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0KESTRELIQ_LOCAL_ENV.bat" call "%~dp0KESTRELIQ_LOCAL_ENV.bat"

if not defined SUPABASE_URL (
  set "SAVE_LOCAL_CONFIG=1"
  echo First-time local Supabase setup
  echo.
  set /p "SUPABASE_URL=Supabase project URL: "
)

if not defined SUPABASE_ANON_KEY (
  set "SAVE_LOCAL_CONFIG=1"
  set /p "SUPABASE_ANON_KEY=Supabase anonymous or publishable key: "
)

if not defined SUPABASE_URL goto :missing_config
if not defined SUPABASE_ANON_KEY goto :missing_config

if defined SAVE_LOCAL_CONFIG (
  >"%~dp0KESTRELIQ_LOCAL_ENV.bat" echo @echo off
  >>"%~dp0KESTRELIQ_LOCAL_ENV.bat" echo set "SUPABASE_URL=%SUPABASE_URL%"
  >>"%~dp0KESTRELIQ_LOCAL_ENV.bat" echo set "SUPABASE_ANON_KEY=%SUPABASE_ANON_KEY%"
  echo.
  echo Local Supabase settings saved outside Git.
)

set "KESTRELIQ_PYTHON=python"
where python >nul 2>nul
if errorlevel 1 set "KESTRELIQ_PYTHON=C:\Users\manju\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if not exist "%KESTRELIQ_PYTHON%" if "%KESTRELIQ_PYTHON%"=="C:\Users\manju\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" goto :missing_python

echo Closing stale KestrelIQ servers on port 8787...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8787 .*LISTENING"') do taskkill /PID %%P /F >nul 2>nul

echo Starting KestrelIQ...
start "KestrelIQ Local Server" /D "%~dp0" "%KESTRELIQ_PYTHON%" app.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8787"
exit /b

:missing_config
echo.
echo Supabase configuration was not saved. Both values are required.
pause
exit /b 1

:missing_python
echo.
echo Python was not found. Open KestrelIQ in Codex once so its bundled runtime is available.
pause
exit /b 1
