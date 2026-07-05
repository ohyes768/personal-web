@echo off
REM ============================================
REM personal-web - rss-relay Development Stop
REM Stop rss-relay backend (8095) + frontend (3006)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping rss-relay Dev Environment
echo ========================================
echo.

echo [1/3] Stopping services by port with process tree...

REM Check and stop port 8095 (rss-relay backend)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8095 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 8095 - PID !PID! with process tree...
    taskkill /F /T /PID !PID! >nul 2>&1
)

REM Check and stop port 3006 (rss-relay frontend)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":3006 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 3006 - PID !PID! with process tree...
    taskkill /F /T /PID !PID! >nul 2>&1
)

echo.
echo [2/3] Cleaning orphaned Python processes...

REM Call separate PowerShell script
powershell -ExecutionPolicy Bypass -File "%~dp0stop-orphan-python.ps1"

echo.
echo [3/3] Closing service windows...

REM Call separate PowerShell script to close windows by port and command
powershell -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1" -Ports "8095,3006" -Commands "uvicorn src.main:app,next.CMD dev"

echo.
echo rss-relay services stopped.
echo.
pause
