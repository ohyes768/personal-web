@echo off
REM ============================================
REM personal-web - News App Development
REM Start News App (3005)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   News Dev Environment Start
echo ========================================
echo.

REM Start News App
echo [1/1] Starting News App (port 3005)...
cd /d "%~dp0..\apps\news"

REM Check node_modules
if not exist "node_modules" (
    echo Installing dependencies...
    cd /d "%~dp0.."
    pnpm install
    cd /d "%~dp0..\apps\news"
)

REM Check .env.local
if not exist ".env.local" (
    echo Creating .env.local file...
    echo BACKEND_URL=http://localhost:8080 > .env.local
)

REM Start News App service
start "News App" cmd /k "pnpm dev"

echo.
echo ========================================
echo   News Service Started!
echo ========================================
echo.
echo Service URL:
echo   * News App:     http://localhost:3005
echo.
pause