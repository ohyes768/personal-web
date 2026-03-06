@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Starting Macro Dev Environment
echo ========================================
echo.

REM Start global-macro-fin
echo Starting global-macro-fin (port 8094)...
cd /d "%~dp0..\backend\global-macro-fin"
if not exist ".venv" (
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)
start "macro-fin" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8094"

timeout /t 2 /nobreak >nul

REM Start Frontend
echo Starting Frontend (port 3000)...
cd /d "%~dp0..\frontend"
if not exist "node_modules" npm install
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
