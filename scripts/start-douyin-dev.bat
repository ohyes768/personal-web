@echo off
REM ============================================
REM personal-web Local Development - Start All
REM Gateway, Frontend, douyin-processor
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   personal-web Dev Environment Start
echo ========================================
echo.

REM [1/3] Start douyin-processor
echo [1/3] Starting douyin-processor (port 8093)...
cd /d "%~dp0..\backend\douyin-processor"

REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
echo Cache cleared.

REM Check .env file
if not exist ".env" (
    echo Creating .env file...
    copy .env.example .env >nul
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
start "douyin-processor" cmd /k ".venv\Scripts\activate && python main.py"

cd /d "%~dp0"
timeout /t 2 /nobreak >nul

REM [2/3] Start Gateway
echo [2/3] Starting Gateway (port 8070)...
cd /d "%~dp0..\gateway"

REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
echo Cache cleared.

REM Check virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
)

REM Check .env file
if not exist ".env" (
    echo Creating .env file...
    copy .env.example .env
    echo DOUYIN_SERVICE_URL=http://localhost:8093 >> .env
    echo DOUYIN_PROCESSOR_URL=http://localhost:8093 >> .env
    echo HOST=0.0.0.0 >> .env
    echo PORT=8070 >> .env
    echo LOG_LEVEL=DEBUG >> .env
    echo REQUEST_TIMEOUT=300.0 >> .env
    echo CORS_ORIGINS=["http://localhost:3000"] >> .env
)

REM Start Gateway (new window)
echo OK: Starting Gateway (port 8070)
start "Gateway" cmd /k ".venv\Scripts\activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8070"

cd /d "%~dp0"
timeout /t 2 /nobreak >nul

REM [3/3] Start Frontend
echo [3/3] Starting Frontend (port 3000)...
cd /d "%~dp0..\frontend"

REM Check node_modules
if not exist "node_modules" (
    echo Installing frontend dependencies...
    npm install
)

REM Check .env.local
if not exist ".env.local" (
    echo Creating .env.local file...
    echo NEXT_PUBLIC_API_BASE_URL=http://localhost:8070 > .env.local
)

REM Start Frontend (new window)
echo OK: Starting Frontend (port 3000)
start "Frontend" cmd /k "npm run dev"

echo.
echo ========================================
echo   All Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Frontend:      http://localhost:3000
echo   * Gateway API:   http://localhost:8070
echo   * Gateway Docs:  http://localhost:8070/docs
echo   * douyin-proc:   http://localhost:8093
echo.
pause
