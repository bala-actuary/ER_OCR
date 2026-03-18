@echo off
setlocal enabledelayedexpansion
title Electoral Roll OCR - Web UI

echo ============================================
echo   Electoral Roll OCR - Web UI
echo ============================================
echo.

REM ── Set Tesseract on PATH ───────────────────────────────────────────────
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    set "PATH=C:\Program Files\Tesseract-OCR;%PATH%"
)
if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" (
    set "PATH=C:\Program Files (x86)\Tesseract-OCR;%PATH%"
)

REM ── Load .env (sets TESSDATA_PREFIX if tessdata was installed locally) ──
if exist "%~dp0.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
        set "%%A=%%B"
    )
)

REM ── Check Python ────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
)
echo [OK] Python found

REM ── Install web UI dependencies if not already present ─────────────────
python -c "import fastapi, uvicorn, aiofiles" >nul 2>&1
if errorlevel 1 (
    echo Installing web dependencies...
    python -m pip install fastapi uvicorn aiofiles psutil --quiet
    if errorlevel 1 (
        echo ERROR: Failed to install web dependencies.
        pause
        exit /b 1
    )
    echo [OK] Web dependencies installed
) else (
    echo [OK] Web dependencies present
)

REM ── Find a free port (try 7000-7009) ────────────────────────────────────
set PORT=7000
for /f %%P in ('python "%~dp0_find_port.py"') do set "PORT=%%P"
echo [OK] Using port %PORT%

echo.
echo ============================================
echo   Press Ctrl+C to stop the server
echo ============================================
echo.

REM ── Change to script directory ──────────────────────────────────────────
cd /d "%~dp0"

REM ── Launch browser after server starts ──────────────────────────────────
start /min "" python -c "import time,webbrowser;time.sleep(2);webbrowser.open('http://localhost:%PORT%')"

REM ── Launch uvicorn ──────────────────────────────────────────────────────
python -m uvicorn web.app:app --host 127.0.0.1 --port %PORT%

echo.
echo Server stopped.
pause
