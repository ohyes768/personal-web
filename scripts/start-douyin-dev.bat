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

REM [1/2] Start douyin-processor
echo [1/2] Starting douyin-processor (port 8093)...
cd /d "%~dp0..\backend\douyin-processor"

REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
if exist "src\__pycache__" rmdir /s /q "src\__pycache__" 2>nul
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
    if "!USE_UV!"=="1" (
        uv venv .venv
        uv sync
    ) else (
        echo ERROR: douyin-processor requires uv package manager
        echo Please install: pip install uv
        pause
        exit /b 1
    )
)

REM Start douyin-processor (new window)
echo OK: Starting douyin-processor (port 8093)
start "douyin-processor" cmd /k ".venv\Scripts\activate && python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8093 --reload"

cd /d "%~dp0"
timeout /t 2 /nobreak >nul

REM [2/2] Start Douyin App
echo [2/2] Starting Douyin App (port 3004)...
cd /d "%~dp0..\apps\douyin"

REM Check node_modules
if not exist "node_modules" (
    echo Installing dependencies...
    cd /d "%~dp0.."
    pnpm install
    cd /d "%~dp0..\apps\douyin"
)

REM Check .env.local
if not exist ".env.local" (
    echo Creating .env.local file...
    echo BACKEND_URL=http://localhost:8080 > .env.local
)

REM Start Douyin App (new window)
echo OK: Starting Douyin App (port 3004)
start "Douyin App" cmd /k "pnpm dev"

echo.
echo ========================================
echo   Douyin Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Douyin App:   http://localhost:3004
echo   * douyin-proc:  http://localhost:8093
echo.
pause