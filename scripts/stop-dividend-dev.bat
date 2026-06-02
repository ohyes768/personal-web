@echo off
REM ============================================
REM personal-web - Dividend App Development Stop
REM Stop dividend-select (8099, legacy 8092) + Dividend App (3003)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping Dividend Dev Environment
echo ========================================
echo.

echo [1/2] Stopping services by port with process tree...

REM Check and stop backend ports. 8092 is the old dividend-select port.
for %%p in (8099 8092) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| find ":%%p " ^| find "LISTENING" 2^>nul') do (
        set "PID=%%a"
        echo Stopping service on port %%p - PID !PID! with process tree...
        taskkill /F /T /PID !PID!
    )
)

REM Check and stop port 3003 (Dividend App)
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
powershell -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1" -Ports "8099,8092,3003" -Commands "pnpm run dev,next.CMD dev,uvicorn src.main:app"

echo.
echo Dividend services stopped.
echo.
pause
