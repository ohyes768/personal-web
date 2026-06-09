@echo off
REM ============================================
REM personal-web - News App Development Stop
REM Stop News App (3005)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping News Dev Environment
echo ========================================
echo.

echo [1/1] Stopping News App by port with process tree...

REM Check and stop port 3005 (News App)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":3005 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 3005 - PID !PID! with process tree...
    taskkill /F /T /PID !PID! >nul 2>&1
)

echo.
echo Closing service windows...

REM Call separate PowerShell script to close windows by port and command
powershell -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1" -Ports "3005" -Commands "pnpm dev"

echo.
echo News service stopped.
echo.
pause