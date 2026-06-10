@echo off
REM ============================================
REM personal-web - Douyin App Development
REM Start douyin-processor (8093) + Douyin App (3004)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Douyin Dev Environment Start
echo ========================================
echo.

set "DOUYIN_API_PORT=8093"
set "DOUYIN_WEB_PORT=3004"

REM [1/2] Start douyin-processor
echo [1/2] Starting douyin-processor (port %DOUYIN_API_PORT%)...
cd /d "%~dp0..\backend\douyin-processor"

REM Kill any existing process on API port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%DOUYIN_API_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %DOUYIN_API_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
if exist "src\__pycache__" rmdir /s /q "src\__pycache__" 2>nul
if exist "src\server\__pycache__" rmdir /s /q "src\server\__pycache__" 2>nul
echo Cache cleared.

REM Check .env file
if not exist ".env" (
    echo Creating .env file...
    copy .env.example .env >nul 2>&1
    echo WARNING: Please configure ALIYUN_ACCESS_KEY in backend\douyin-processor\.env
)

REM Check virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    uv venv .venv
    uv sync
)

REM Start douyin-processor (new window)
echo OK: Starting douyin-processor (port %DOUYIN_API_PORT%)
start "douyin-processor" cmd /k ".venv\Scripts\activate && python -m uvicorn src.server.main:app --host 0.0.0.0 --port %DOUYIN_API_PORT% --reload"

cd /d "%~dp0"
timeout /t 2 /nobreak >nul

REM [2/2] Start Douyin App
echo [2/2] Starting Douyin App (port %DOUYIN_WEB_PORT%)...
cd /d "%~dp0..\apps\douyin"

REM Kill any existing process on frontend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%DOUYIN_WEB_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %DOUYIN_WEB_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Check node_modules
if not exist "node_modules" (
    echo Installing dependencies...
    cd /d "%~dp0.."
    pnpm install
    cd /d "%~dp0..\apps\douyin"
)

REM Ensure .env.local exists with required BFF backend URLs
if not exist ".env.local" (
    echo Creating .env.local file...
    (
        echo # BFF catch-all（dev 用；线上被 nginx 绕过）
        echo # 后端真实路由是 /api/videos、/api/aweme/...、/api/stats，没有 /api/douyin/ 这一层
        echo DOUYIN_BACKEND_URL=http://localhost:%DOUYIN_API_PORT%/api
        echo AWEME_BACKEND_URL=http://localhost:%DOUYIN_API_PORT%/api/aweme
    ) > .env.local
)

findstr /B /C:"DOUYIN_BACKEND_URL=" ".env.local" >nul 2>&1
if errorlevel 1 (
    echo Adding DOUYIN_BACKEND_URL to .env.local...
    echo DOUYIN_BACKEND_URL=http://localhost:%DOUYIN_API_PORT%/api >> .env.local
)

findstr /B /C:"AWEME_BACKEND_URL=" ".env.local" >nul 2>&1
if errorlevel 1 (
    echo Adding AWEME_BACKEND_URL to .env.local...
    echo AWEME_BACKEND_URL=http://localhost:%DOUYIN_API_PORT%/api/aweme >> .env.local
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content '.env.local') -replace '^DOUYIN_BACKEND_URL=.*', 'DOUYIN_BACKEND_URL=http://localhost:%DOUYIN_API_PORT%/api' | Set-Content '.env.local'"
powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content '.env.local') -replace '^AWEME_BACKEND_URL=.*', 'AWEME_BACKEND_URL=http://localhost:%DOUYIN_API_PORT%/api/aweme' | Set-Content '.env.local'"

REM Start Douyin App (new window)
echo OK: Starting Douyin App (port %DOUYIN_WEB_PORT%)
start "Douyin App" cmd /k "cd /d "%~dp0..\apps\douyin" && .\node_modules\.bin\next.CMD dev -p %DOUYIN_WEB_PORT%"

echo.
echo ========================================
echo   Douyin Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Douyin App:   http://localhost:%DOUYIN_WEB_PORT%/douyin
echo   * douyin-proc:  http://localhost:%DOUYIN_API_PORT%
echo.
pause
