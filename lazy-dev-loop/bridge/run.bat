@echo off
REM ──────────────────────────────────────────────────────────────────────────
REM  Lazy Developer Loop — Windows startup script
REM
REM  NOTICE: Linux is now the primary supported platform.
REM  This script is retained for future Windows/WSL work and
REM  is NOT tested as part of the current release.
REM ──────────────────────────────────────────────────────────────────────────

set "SCRIPT_DIR=%~dp0"
set "APP_MODULE=main:app"
set "HOST=0.0.0.0"
set "PORT=7777"

REM Try known venv locations relative to the repo root
set "UVICORN_CMD="
if exist "%SCRIPT_DIR%..\..\.venv\Scripts\uvicorn.exe" set "UVICORN_CMD=%SCRIPT_DIR%..\..\.venv\Scripts\uvicorn.exe"
if exist "%SCRIPT_DIR%..\..\venv\Scripts\uvicorn.exe" set "UVICORN_CMD=%SCRIPT_DIR%..\..\venv\Scripts\uvicorn.exe"

if "%UVICORN_CMD%"=="" (
  where uvicorn >nul 2>nul
  if errorlevel 1 (
    echo ERROR: uvicorn not found.
    echo.
    echo   Tried: %SCRIPT_DIR%..\..\.venv\Scripts\uvicorn.exe
    echo   Tried: %SCRIPT_DIR%..\..\venv\Scripts\uvicorn.exe
    echo.
    echo   Activate your venv or install dependencies:
    echo     pip install -r "%SCRIPT_DIR%requirements.txt"
    pause
    exit /b 1
  )
  set "UVICORN_CMD=uvicorn"
)

echo ============================================
echo   Lazy Developer Loop Bridge
echo ============================================
echo   Module : %APP_MODULE%
echo   Host   : %HOST%
echo   Port   : %PORT%
echo   Uvicorn: %UVICORN_CMD%
echo ============================================
echo.

REM Release port if already in use
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":7777 "') do (
  taskkill /F /PID %%p >nul 2>nul
)

"%UVICORN_CMD%" %APP_MODULE% --host %HOST% --port %PORT%
pause
