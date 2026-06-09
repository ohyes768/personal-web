@echo off
REM ============================================
REM personal-web - Fund Flow App Development Stop
REM Stop Fund Flow App (3002)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping Fund Flow Dev Environment
echo ========================================
echo.

echo [1/1] Stopping Fund Flow App by port with process tree...

REM Check and stop port 3002 (Fund Flow App)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":3002 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 3002 - PID !PID! with process tree...
    taskkill /F /T /PID !PID! >nul 2>&1
)

echo.
echo Closing service windows...

REM Call separate PowerShell script to close windows by port and command
powershell -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1" -Ports "3002" -Commands "pnpm dev"

echo.
echo Fund Flow service stopped.
echo.
pause