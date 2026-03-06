@echo off
REM ============================================
REM personal-web Local Development - Stop
REM Stop global-macro-fin (8094) + Frontend (3000) + all related children
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping Dev Environment
echo ========================================
echo.

echo [1/2] Stopping services by port with process tree...

REM Check and stop port 8094
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8094 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 8094 - PID !PID! with process tree...
    taskkill /F /T /PID !PID! >nul 2>&1
)

REM Check and stop port 3000
for /f "tokens=5" %%a in ('netstat -aon ^| find ":3000 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 3000 - PID !PID! with process tree...
    taskkill /F /T /PID !PID! >nul 2>&1
)

echo.
echo [2/2] Cleaning orphaned Python processes...

REM Call separate PowerShell script
powershell -ExecutionPolicy Bypass -File "%~dp0stop-orphan-python.ps1"

echo.
echo Closing service windows...

REM Call separate PowerShell script to close windows
powershell -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1" "macro-fin,Frontend"

echo.
echo All services stopped.
echo.
pause
