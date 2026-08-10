@echo off
REM ============================================
REM personal-web - Economic App Development
REM Start global-macro-fin (8094) + Economic App (3001)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Economic Dev Environment Start
echo ========================================
echo.

set "MACRO_API_PORT=8094"
set "ECONOMIC_WEB_PORT=3001"

REM [1/2] Start global-macro-fin
echo [1/2] Starting global-macro-fin (port %MACRO_API_PORT%)...
cd /d "%~dp0..\backend\global-macro-fin"

REM Kill any existing process on API port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%MACRO_API_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %MACRO_API_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Check backend .env (FRED_API_KEY is mandatory, missing = crash on startup)
if not exist ".env" (
    echo [ERROR] backend\global-macro-fin\.env not found.
    echo         Copy .env.example to .env and fill in FRED_API_KEY.
    echo         See: backend\global-macro-fin\.env.example
    goto :error
)
findstr /B /C:"FRED_API_KEY=" ".env" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] FRED_API_KEY missing in backend\global-macro-fin\.env
    goto :error
)

REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "src\__pycache__" rmdir /s /q "src\__pycache__" 2>nul
if exist "src\api\__pycache__" rmdir /s /q "src\api\__pycache__" 2>nul
if exist "src\services\__pycache__" rmdir /s /q "src\services\__pycache__" 2>nul
if exist "src\utils\__pycache__" rmdir /s /q "src\utils\__pycache__" 2>nul
echo Cache cleared.

REM Setup virtual environment (uv is much faster than pip)
if not exist ".venv" (
    echo Creating virtual environment with uv...
    uv venv .venv
    uv sync
)

REM Start global-macro-fin service
start "macro-fin" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port %MACRO_API_PORT%"

timeout /t 2 /nobreak >nul

REM [2/2] Start Economic App
echo [2/2] Starting Economic App (port %ECONOMIC_WEB_PORT%)...
cd /d "%~dp0..\apps\economic"

REM Kill any existing process on frontend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%ECONOMIC_WEB_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %ECONOMIC_WEB_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Check node_modules
if not exist "node_modules" (
    echo Installing dependencies...
    cd /d "%~dp0.."
    pnpm install
    cd /d "%~dp0..\apps\economic"
)

REM Check .env.local
if not exist ".env.local" (
    echo Creating .env.local file...
    echo BACKEND_URL=http://localhost:%MACRO_API_PORT% > .env.local
)

REM Start Economic App service
start "Economic App" cmd /k "pnpm dev"

echo.
echo ========================================
echo   Economic Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Economic App:  http://localhost:%ECONOMIC_WEB_PORT%
echo   * Macro-Fin:     http://localhost:%MACRO_API_PORT%
echo.
goto :eof

:error
echo.
echo Startup aborted due to configuration error above.
pause
exit /b 1