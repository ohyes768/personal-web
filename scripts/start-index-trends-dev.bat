@echo off
REM ============================================
REM personal-web - Index Trends Development
REM Start index-trends backend (8100) + frontend (3010)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Index Trends Dev Environment Start
echo ========================================
echo.

set "INDEX_TRENDS_API_PORT=8100"
set "INDEX_TRENDS_WEB_PORT=3010"

REM [1/2] Start backend
echo [1/2] Starting index-trends backend (port %INDEX_TRENDS_API_PORT%)...
cd /d "%~dp0..\backend\index-trends"

REM Kill any existing process on API port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%INDEX_TRENDS_API_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %INDEX_TRENDS_API_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "src\__pycache__" rmdir /s /q "src\__pycache__" 2>nul
if exist "src\core\__pycache__" rmdir /s /q "src\core\__pycache__" 2>nul
if exist "src\data\__pycache__" rmdir /s /q "src\data\__pycache__" 2>nul
if exist "src\services\__pycache__" rmdir /s /q "src\services\__pycache__" 2>nul
if exist "src\api\__pycache__" rmdir /s /q "src\api\__pycache__" 2>nul
echo Cache cleared.

REM Setup virtual environment (uv is much faster than pip)
if not exist ".venv" (
    echo Creating virtual environment with uv...
    uv venv .venv
    uv sync
)

REM Start backend（钉钉 webhook 留空则周报保存为 no_channel，不发送）
start "index-trends-backend" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port %INDEX_TRENDS_API_PORT%"

timeout /t 2 /nobreak >nul

REM [2/2] Start frontend
echo [2/2] Starting index-trends frontend (port %INDEX_TRENDS_WEB_PORT%)...
cd /d "%~dp0..\apps\index-trends"

REM Kill any existing process on frontend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%INDEX_TRENDS_WEB_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %INDEX_TRENDS_WEB_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Check node_modules
if not exist "node_modules" (
    echo Installing dependencies...
    pnpm install
)

REM Start frontend（rewrites 代理 /api/index-trends → localhost:8100）
start "index-trends-frontend" cmd /k "pnpm dev"

echo.
echo ========================================
echo   Index Trends Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Frontend:  http://localhost:%INDEX_TRENDS_WEB_PORT%/index-trends
echo   * Backend:   http://localhost:%INDEX_TRENDS_API_PORT%/api/health
echo   * API docs:  http://localhost:%INDEX_TRENDS_API_PORT%/docs
echo.
goto :eof
