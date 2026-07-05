@echo off
REM ============================================
REM personal-web - rss-relay Development Start
REM Start rss-relay backend (8095) + frontend (3006)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   rss-relay Dev Environment Start
echo ========================================
echo.

set "RSS_RELAY_PORT=8095"
set "RSS_RELAY_WEB_PORT=3006"

REM [1/2] Start rss-relay backend
echo [1/2] Starting rss-relay backend (port %RSS_RELAY_PORT%)...
cd /d "%~dp0..\backend\rss-relay"

REM Kill any existing process on backend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%RSS_RELAY_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %RSS_RELAY_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
if exist "src\__pycache__" rmdir /s /q "src\__pycache__" 2>nul
echo Cache cleared.

REM Check .env file
REM NOTE: if 块内的 echo 不能含 () 否则 cmd 误解析为块结束
if not exist ".env" (
    echo Creating .env file from .env.example...
    copy .env.example .env >nul 2>&1
    echo WARNING: Please set RSS_RELAY_TOKEN in backend\rss-relay\.env
    echo          Without a token, all RSS requests return 401
)

REM Setup virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    uv venv .venv
    uv sync
)

REM Start rss-relay backend (new window)
start "rss-relay-backend" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --host 0.0.0.0 --port %RSS_RELAY_PORT% --reload"

timeout /t 2 /nobreak >nul

REM [2/2] Start rss-relay frontend
echo [2/2] Starting rss-relay frontend (port %RSS_RELAY_WEB_PORT%)...
cd /d "%~dp0..\apps\rss-relay"

REM Kill any existing process on frontend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%RSS_RELAY_WEB_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %RSS_RELAY_WEB_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Check node_modules
if not exist "node_modules" (
    echo Installing frontend dependencies...
    cd /d "%~dp0.."
    pnpm install
    cd /d "%~dp0..\apps\rss-relay"
)

REM Ensure .env.local exists (BFF 转发到后端)
if not exist ".env.local" (
    echo Creating .env.local file...
    echo BACKEND_URL=http://localhost:%RSS_RELAY_PORT%/api > .env.local
)

REM Start rss-relay frontend (new window)
start "rss-relay-frontend" cmd /k "cd /d "%~dp0..\apps\rss-relay" && .\node_modules\.bin\next.CMD dev -p %RSS_RELAY_WEB_PORT%"

echo.
echo ========================================
echo   rss-relay Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Backend:      http://localhost:%RSS_RELAY_PORT%
echo   * Frontend:     http://localhost:%RSS_RELAY_WEB_PORT%/rss
echo   * RSS feed:     http://localhost:%RSS_RELAY_PORT%/api/rss.xml?token=YOUR_TOKEN
echo   * Push API:     POST http://localhost:%RSS_RELAY_PORT%/api/post
echo.
pause
