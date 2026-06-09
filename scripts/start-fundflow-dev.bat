@echo off
REM ============================================
REM personal-web - Fund Flow App Development
REM Start global-macro-fin (8094) + Fund Flow App (3002)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Fund Flow Dev Environment Start
echo ========================================
echo.

REM [1/2] Start global-macro-fin
echo [1/2] Starting global-macro-fin (port 8094)...
cd /d "%~dp0..\backend\global-macro-fin"

REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "src\__pycache__" rmdir /s /q "src\__pycache__" 2>nul
if exist "src\api\__pycache__" rmdir /s /q "src\api\__pycache__" 2>nul
if exist "src\services\__pycache__" rmdir /s /q "src\services\__pycache__" 2>nul
if exist "src\utils\__pycache__" rmdir /s /q "src\utils\__pycache__" 2>nul
echo Cache cleared.

REM Setup virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)

REM Start global-macro-fin service
start "macro-fin" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8094"

timeout /t 2 /nobreak >nul

REM [2/2] Start Fund Flow App
echo [2/2] Starting Fund Flow App (port 3002)...
cd /d "%~dp0..\apps\fund-flow"

REM Check node_modules
if not exist "node_modules" (
    echo Installing dependencies...
    cd /d "%~dp0.."
    pnpm install
    cd /d "%~dp0..\apps\fund-flow"
)

REM Check .env.local
if not exist ".env.local" (
    echo Creating .env.local file...
    echo BACKEND_URL=http://localhost:8094 > .env.local
)

REM Start Fund Flow App service
start "Fund Flow App" cmd /k "pnpm dev"

echo.
echo ========================================
echo   Fund Flow Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Fund Flow App:  http://localhost:3002/fund-flow
echo   * Macro-Fin API: http://localhost:8094
echo.
pause