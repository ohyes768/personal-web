@echo off
chcp 65001 >nul
cd /d "%~dp0.."
cd gateway

echo ======================================
echo Gateway Development Server
echo ======================================
echo Current directory: %CD%
echo ======================================

if not exist ".env" (
    if exist ".env.example" (
        echo Creating .env file...
        copy .env.example .env
    ) else (
        echo ERROR: .env.example not found
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv .venv
)

echo Installing dependencies...
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet

mkdir ..\scripts\logs 2>nul

echo ======================================
echo Starting Gateway server...
echo API Docs: http://localhost:8080/docs
echo Health: http://localhost:8080/api/health
echo ======================================
echo.

.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
