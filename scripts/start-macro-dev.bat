@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Starting Macro Dev Environment
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

REM [2/2] Start Frontend
echo [2/2] Starting Frontend (port 3000)...
cd /d "%~dp0..\frontend"

REM Setup node modules
if not exist "node_modules" (
    echo Installing frontend dependencies...
    npm install
)

REM Start Frontend service
start "Frontend" cmd /k "npm run dev"

echo.
echo ========================================
echo   Macro Dev Environment Started
echo ========================================
echo.
echo Frontend:   http://localhost:3000
echo Macro-Fin:  http://localhost:8094
echo.
pause
