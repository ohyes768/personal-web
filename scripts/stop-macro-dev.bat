@echo off
REM ============================================
REM personal-web - Economic App Development Stop
REM Stop global-macro-fin (8094) + Economic App (3001)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping Economic Dev Environment
echo ========================================
echo.

echo [1/2] Stopping services by port with process tree...

REM Check and stop port 8094 (global-macro-fin)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8094 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 8094 - PID !PID! with process tree...
    taskkill /F /T /PID !PID! >nul 2>&1
)

REM Check and stop port 3001 (Economic App)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":3001 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 3001 - PID !PID! with process tree...
    taskkill /F /T /PID !PID! >nul 2>&1
)

echo.
echo [2/2] Cleaning orphaned Python processes...

REM Call separate PowerShell script
powershell -ExecutionPolicy Bypass -File "%~dp0stop-orphan-python.ps1"

echo.
echo Closing service windows...

REM Call separate PowerShell script to close windows by port and command
powershell -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1" -Ports "8094" -Commands "pnpm dev"

echo.
echo Economic services stopped.
echo.
pause