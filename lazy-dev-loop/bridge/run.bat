@echo off
REM Lazy Developer Loop — Bridge startup script for native Windows (cmd.exe)

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

"%UVICORN_CMD%" %APP_MODULE% --host %HOST% --port %PORT%
pause
