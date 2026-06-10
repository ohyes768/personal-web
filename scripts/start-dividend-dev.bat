@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Starting Dividend Dev Environment
echo ========================================
echo.

set "DIVIDEND_API_PORT=8092"
set "DIVIDEND_WEB_PORT=3003"

REM [1/2] Start dividend-select
echo [1/2] Starting dividend-select (port %DIVIDEND_API_PORT%)...
cd /d "%~dp0..\backend\dividend-select"

REM Kill any existing process on API port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%DIVIDEND_API_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %DIVIDEND_API_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

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

REM Start dividend-select service with --reload flag
start /d "%~dp0..\backend\dividend-select" "dividend-select" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port %DIVIDEND_API_PORT%"

timeout /t 2 /nobreak >nul

REM [2/2] Start Frontend (dividend app)
echo [2/2] Starting Frontend (port %DIVIDEND_WEB_PORT%)...
cd /d "%~dp0..\apps\dividend"

REM Kill any existing process on frontend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%DIVIDEND_WEB_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %DIVIDEND_WEB_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Setup node modules
if not exist "node_modules" (
    echo Installing frontend dependencies...
    cmd /c "cd /d %CD% && pnpm install"
)

REM Check .env.local
if not exist ".env.local" (
    echo Creating .env.local file...
    echo NEXT_PUBLIC_API_BASE_URL=http://localhost:%DIVIDEND_API_PORT% > .env.local
)

findstr /B /C:"NEXT_PUBLIC_API_BASE_URL=" ".env.local" >nul 2>&1
if errorlevel 1 (
    echo Adding NEXT_PUBLIC_API_BASE_URL to .env.local...
    echo NEXT_PUBLIC_API_BASE_URL=http://localhost:%DIVIDEND_API_PORT% >> .env.local
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content '.env.local') -replace '^NEXT_PUBLIC_API_BASE_URL=.*', 'NEXT_PUBLIC_API_BASE_URL=http://localhost:%DIVIDEND_API_PORT%' | Set-Content '.env.local'"

REM Ensure BACKEND_URL exists (BFF route uses it to proxy /api/dividend/* to backend)
findstr /B /C:"BACKEND_URL=" ".env.local" >nul 2>&1
if errorlevel 1 (
    echo Adding BACKEND_URL to .env.local...
    echo BACKEND_URL=http://localhost:%DIVIDEND_API_PORT%/api/dividend >> .env.local
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content '.env.local') -replace '^BACKEND_URL=.*', 'BACKEND_URL=http://localhost:%DIVIDEND_API_PORT%/api/dividend' | Set-Content '.env.local'"

REM Start Frontend service directly (API already verified running)
start "Frontend" cmd /k "cd /d "%~dp0..\apps\dividend" && .\node_modules\.bin\next.CMD dev -p %DIVIDEND_WEB_PORT%"

echo.
echo ========================================
echo   Dividend Dev Environment Started
echo ========================================
echo.
echo Frontend:        http://localhost:%DIVIDEND_WEB_PORT%/
echo Dividend-Select: http://localhost:%DIVIDEND_API_PORT%  (submodule doc: 8092)
echo.
pause
