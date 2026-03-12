@echo off
REM ============================================
REM personal-web Local Development - Stop
REM Stop dividend-select (8092) + Frontend (3000) + all related children
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping Dev Environment
echo ========================================
echo.

echo [1/2] Stopping services by port with process tree...

REM Check and stop port 8092
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8092 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 8092 - PID !PID! with process tree...
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

REM Call separate PowerShell script to close windows by port and command
powershell -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1" -Ports "8092" -Commands "pnpm run dev"

echo.
echo All services stopped.
echo.
pause