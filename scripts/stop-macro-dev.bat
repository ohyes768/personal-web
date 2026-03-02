@echo off
REM ============================================
REM personal-web Local Development - Stop
REM ============================================

echo.
echo ========================================
echo   Stopping Dev Environment
echo ========================================
echo.

echo Stopping services...

REM Run PowerShell script
powershell -ExecutionPolicy Bypass -File "%~dp0stop-services.ps1"

timeout /t 2 /nobreak >nul

REM Fallback: kill by port
echo Force checking ports...
for %%p in (8070 8094 3000) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| find ":%%p " ^| find "LISTENING" 2^>nul') do (
        if "%%a" neq "" taskkill /F /PID %%a >nul 2>&1
    )
)

echo.
pause
