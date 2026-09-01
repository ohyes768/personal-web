@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Starting Fund-Select Backend
echo ========================================
echo.

set "FUND_API_PORT=8095"

cd /d "%~dp0..\backend"

REM Kill any existing process on API port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%FUND_API_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %FUND_API_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Setup virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    uv venv .venv
    uv sync
)

REM Ensure data dir exists
if not exist "data" mkdir data

start "fund-select-backend" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port %FUND_API_PORT%"

echo.
echo Fund-Select Backend: http://localhost:%FUND_API_PORT%/api/funds/health
echo.
pause
