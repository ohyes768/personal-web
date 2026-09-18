@echo off
REM ============================================
REM personal-web - Housing Map Development
REM Start housing-map backend (8096) + frontend (3007)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Housing Map Dev Environment Start
echo ========================================
echo.

set "HOUSING_API_PORT=8096"
set "HOUSING_WEB_PORT=3007"

REM [1/2] Start housing-map backend
echo [1/2] Starting housing-map backend (port %HOUSING_API_PORT%)...
cd /d "%~dp0..\backend\housing-map"

REM Kill any existing process on API port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%HOUSING_API_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %HOUSING_API_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "src\__pycache__" rmdir /s /q "src\__pycache__" 2>nul
if exist "src\api\__pycache__" rmdir /s /q "src\api\__pycache__" 2>nul
if exist "src\services\__pycache__" rmdir /s /q "src\services\__pycache__" 2>nul
if exist "src\core\__pycache__" rmdir /s /q "src\core\__pycache__" 2>nul
echo Cache cleared.

REM Setup virtual environment (uv is much faster than pip)
if not exist ".venv" (
    echo Creating virtual environment with uv...
    uv venv .venv
    uv sync
)

REM Start housing-map backend service
start "housing-map" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port %HOUSING_API_PORT%"

timeout /t 2 /nobreak >nul

REM [2/2] Start Housing Map frontend
echo [2/2] Starting Housing Map frontend (port %HOUSING_WEB_PORT%)...
cd /d "%~dp0..\apps\housing-map"

REM Kill any existing process on frontend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%HOUSING_WEB_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %HOUSING_WEB_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Check node_modules
if not exist "node_modules" (
    echo Installing dependencies...
    cd /d "%~dp0.."
    pnpm install
    cd /d "%~dp0..\apps\housing-map"
)

REM Check .env.local (Gaode map keys are required for the map to load)
if not exist ".env.local" (
    echo [WARN] apps\housing-map\.env.local not found.
    echo        Map will not load without Gaode keys. Create .env.local with:
    echo          NEXT_PUBLIC_GAODE_MAP_KEY=your-key
    echo          NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY=your-security-key
)

REM Start Housing Map frontend service
start "Housing Map" cmd /k "pnpm dev"

echo.
echo ========================================
echo   Housing Map Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Housing Map frontend: http://localhost:%HOUSING_WEB_PORT%/map
echo   * Housing Map backend:  http://localhost:%HOUSING_API_PORT%/api/health
echo.
goto :eof

:error
echo.
echo Startup aborted due to configuration error above.
pause
exit /b 1
