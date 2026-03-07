@echo off
REM ============================================
REM personal-web Local Development - Stop All
REM Stop douyin-processor (8093), Frontend (3000)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping Dev Environment
echo ========================================
echo.

echo [1/2] Stopping services by port with process tree...

REM Check and stop port 8093 (douyin-processor)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8093 " ^| find "LISTENING" 2^>nul') do (
    set "PID=%%a"
    echo Stopping service on port 8093 - PID !PID! with process tree...
    taskkill /F /T /PID !PID! >nul 2>&1
)

REM Check and stop port 3000 (Frontend)
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
powershell -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1" "douyin-processor,Frontend"

echo.
echo All services stopped.
echo.
pause