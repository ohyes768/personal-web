@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Starting Dividend Dev Environment
echo ========================================
echo.

REM [1/2] Start dividend-select
echo [1/2] Starting dividend-select (port 8092)...
cd /d "%~dp0..\backend\dividend-select"

REM Clear Python cache
echo Cleaning Python cache...
if exist "src\__pycache__" rmdir /s /q "src\__pycache__" 2>nul
if exist "src\api\__pycache__" rmdir /s /q "src\api\__pycache__" 2>nul
if exist "src\services\__pycache__" rmdir /s /q "src\services\__pycache__" 2>nul
if exist "src\utils\__pycache__" rmdir /s /q "src\utils\__pycache__" 2>nul
if exist "src\data\__pycache__" rmdir /s /q "src\data\__pycache__" 2>nul
if exist "src\core\__pycache__" rmdir /s /q "src\core\__pycache__" 2>nul
echo Cache cleared.

REM Setup virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    uv venv .venv
    uv sync
)

REM Start dividend-select service
start /d "%~dp0..\backend\dividend-select" "dividend-select" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8092"

timeout /t 2 /nobreak >nul

REM [2/2] Start Frontend
echo [2/2] Starting Frontend (port 3000)...
cd /d "%~dp0..\frontend"

REM Setup node modules
if not exist "node_modules" (
    echo Installing frontend dependencies...
    cmd /c "cd /d %CD% && pnpm install"
)

REM Check .env.local
if not exist ".env.local" (
    echo Creating .env.local file...
    echo DIVIDEND_API_URL=http://localhost:8092 > .env.local
)

REM Start Frontend service
start /d "%~dp0..\frontend" "Frontend" cmd /k "pnpm run dev"

echo.
echo ========================================
echo   Dividend Dev Environment Started
echo ========================================
echo.
echo Frontend:        http://localhost:3000
echo Dividend-Select: http://localhost:8092
echo.
pause