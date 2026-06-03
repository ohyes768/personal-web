@echo off
REM ============================================
REM personal-web - Dividend App Development Stop
REM Stop dividend-select (8092) + Dividend App (3003)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping Dividend Dev Environment
REM ========================================

echo.
echo [1/2] Stopping services by port with process tree...

REM Stop dividend-select on port 8092
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8092 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 8092 - PID !PID! with process tree...
    taskkill /F /T /PID !PID!
)

REM Stop Dividend App on port 3003
for /f "tokens=5" %%a in ('netstat -aon ^| find ":3003 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 3003 - PID !PID! with process tree...
    taskkill /F /T /PID !PID!
)

echo.
echo [2/2] Cleaning orphaned Python processes...

REM Call separate PowerShell script
powershell -ExecutionPolicy Bypass -File "%~dp0stop-orphan-python.ps1"

echo.
echo Closing service windows...

REM Call separate PowerShell script to close windows by port and command
powershell -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1" -Ports "8092,3003" -Commands "pnpm run dev,next.CMD dev,uvicorn src.main:app"

echo.
echo Dividend services stopped.
echo.
pause
