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

REM [1/5] Check environment
echo [1/5] Checking development environment...

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    pause
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js not found
    pause
    exit /b 1
)

where uv >nul 2>&1
if errorlevel 1 (
    echo WARNING: uv not found, attempting to use pip...
    set USE_UV=0
) else (
    set USE_UV=1
)
echo OK: Environment check passed
echo.

REM [2/5] Start douyin-processor
echo [2/5] Starting douyin-processor...
cd /d "%~dp0..\backend\douyin-processor"

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

REM [3/5] Start Gateway
echo [3/5] Starting Gateway...
cd /d "%~dp0..\gateway"

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

REM [4/5] Start Frontend
echo [4/5] Starting Frontend...
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

cd /d "%~dp0"
timeout /t 3 /nobreak >nul

REM [5/5] Wait and check services
echo [5/5] Waiting for services to start...
echo.
timeout /t 5 /nobreak >nul

REM Check service status
echo ========================================
echo   Service Status Check
echo ========================================

REM Check douyin-processor
curl -s http://localhost:8093/health >nul 2>&1
if errorlevel 1 (
    echo X douyin-processor (8093) - Not responding
) else (
    echo OK douyin-processor (8093) - Running
)

REM Check Gateway
curl -s http://localhost:8070/api/health >nul 2>&1
if errorlevel 1 (
    echo X Gateway (8070) - Not responding
) else (
    echo OK Gateway (8070) - Running
)

REM Check Frontend
curl -s http://localhost:3000 >nul 2>&1
if errorlevel 1 (
    echo ... Frontend (3000) - Starting...
) else (
    echo OK Frontend (3000) - Running
)

echo.
echo ========================================
echo   All Services Started!
echo ========================================
echo.
echo Service URLs:
echo   - Frontend:      http://localhost:3000
echo   - Gateway API:   http://localhost:8070
echo   - Gateway Docs:  http://localhost:8070/docs
echo   - douyin-proc:   http://localhost:8093
echo.
echo TIP: Close individual service windows to stop each service
echo.
pause
