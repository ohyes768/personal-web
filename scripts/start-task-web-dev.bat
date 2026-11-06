@echo off
REM ============================================
REM personal-web - Task Web Development
REM Start task-web backend (8101) + frontend (3011)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Task Web Dev Environment Start
echo ========================================
echo.

set "TASK_WEB_API_PORT=8101"
set "TASK_WEB_WEB_PORT=3011"

REM [1/2] Start backend
echo [1/2] Starting task-web backend (port %TASK_WEB_API_PORT%)...
cd /d "%~dp0..\backend\task-web"

REM Kill any existing process on API port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%TASK_WEB_API_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %TASK_WEB_API_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Setup virtual environment (uv is much faster than pip)
if not exist ".venv" (
    echo Creating virtual environment with uv...
    uv venv .venv
    uv sync --extra dev
)

REM Start backend（本地未配置 TASK_WEB_ADMIN_PASSWORD 时手动执行返回 403）
start "task-web-backend" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port %TASK_WEB_API_PORT%"

timeout /t 2 /nobreak >nul

REM [2/2] Start frontend
echo [2/2] Starting task-web frontend (port %TASK_WEB_WEB_PORT%)...
cd /d "%~dp0..\apps\task-web"

REM Kill any existing process on frontend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%TASK_WEB_WEB_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %TASK_WEB_WEB_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Check node_modules
if not exist "node_modules" (
    echo Installing dependencies...
    pnpm install
)

REM Start frontend（rewrites 代理 /api/task-web → localhost:8101）
start "task-web-frontend" cmd /k "pnpm dev"

echo.
echo ========================================
echo   Task Web Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Frontend:  http://localhost:%TASK_WEB_WEB_PORT%/tasks
echo   * Backend:   http://localhost:%TASK_WEB_API_PORT%/api/health
echo   * API docs:  http://localhost:%TASK_WEB_API_PORT%/docs
echo.
goto :eof
