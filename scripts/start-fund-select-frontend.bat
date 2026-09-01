@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Starting Fund-Select Frontend
echo ========================================
echo.

set "FUND_WEB_PORT=3005"
set "FUND_API_PORT=8095"

cd /d "%~dp0..\frontend"

REM Kill any existing process on frontend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%FUND_WEB_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %FUND_WEB_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Setup node modules
if not exist "node_modules" (
    echo Installing frontend dependencies...
    cmd /c "cd /d %CD% && pnpm install"
)

REM Ensure .env.local has BACKEND_URL (BFF route uses it)
if not exist ".env.local" (
    echo Creating .env.local file...
    echo BACKEND_URL=http://localhost:%FUND_API_PORT% > .env.local
)

findstr /B /C:"BACKEND_URL=" ".env.local" >nul 2>&1
if errorlevel 1 (
    echo Adding BACKEND_URL to .env.local...
    echo BACKEND_URL=http://localhost:%FUND_API_PORT% >> .env.local
)

start "fund-select-frontend" cmd /k "cd /d %~dp0..\frontend && .\node_modules\.bin\next.CMD dev -p %FUND_WEB_PORT%"

echo.
echo Fund-Select Frontend: http://localhost:%FUND_WEB_PORT%/funds
echo.
pause
