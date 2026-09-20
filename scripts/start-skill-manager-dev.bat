@echo off
REM ============================================
REM personal-web - Skill Manager Development
REM Start skill-manager backend (8097) + frontend (3008)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Skill Manager Dev Environment Start
echo ========================================
echo.

set "SKILL_API_PORT=8097"
set "SKILL_WEB_PORT=3008"

REM Backend Settings 受限 NAS 路径（design 2.2），本地开发指向 Windows 源目录与临时目录
REM 已在环境中设置过的变量（如真实密码）不会被覆盖
if not defined SKILLS_SOURCE_ROOT set "SKILLS_SOURCE_ROOT=F:\personal-projects\skills"
if not defined GITHUB_SKILL_CACHE_ROOT set "GITHUB_SKILL_CACHE_ROOT=%~dp0..\.skill-manager-dev\github-cache"
if not defined SKILL_MANAGER_STATE_DIR set "SKILL_MANAGER_STATE_DIR=%~dp0..\.skill-manager-dev\state"
if not defined OPENCLAW_SKILLS_ROOT set "OPENCLAW_SKILLS_ROOT=%~dp0..\.skill-manager-dev\targets\openclaw"
if not defined HERMES_SKILLS_ROOT set "HERMES_SKILLS_ROOT=%~dp0..\.skill-manager-dev\targets\hermes"
if not defined SKILL_MANAGER_TARGETS_MOUNT_ROOT set "SKILL_MANAGER_TARGETS_MOUNT_ROOT=%~dp0..\.skill-manager-dev\targets"
REM 仅本地开发占位密码；真实密码通过环境变量注入，绝不写入本脚本
if not defined SKILL_MANAGER_ADMIN_PASSWORD set "SKILL_MANAGER_ADMIN_PASSWORD=dev-only-not-for-production"

REM Ensure required directories exist (config.py 启动时要求目录已存在)
if not exist "%GITHUB_SKILL_CACHE_ROOT%" mkdir "%GITHUB_SKILL_CACHE_ROOT%"
if not exist "%SKILL_MANAGER_STATE_DIR%" mkdir "%SKILL_MANAGER_STATE_DIR%"
if not exist "%OPENCLAW_SKILLS_ROOT%" mkdir "%OPENCLAW_SKILLS_ROOT%"
if not exist "%HERMES_SKILLS_ROOT%" mkdir "%HERMES_SKILLS_ROOT%"

REM [1/2] Start skill-manager backend
echo [1/2] Starting skill-manager backend (port %SKILL_API_PORT%)...
cd /d "%~dp0..\backend\skill-manager"

REM Kill any existing process on API port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%SKILL_API_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %SKILL_API_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Setup virtual environment (uv is much faster than pip)
if not exist ".venv" (
    echo Creating virtual environment with uv...
    uv sync
)

REM Start skill-manager backend service
start "skill-manager-backend" cmd /k "uv run uvicorn src.main:app --reload --host 0.0.0.0 --port %SKILL_API_PORT%"

timeout /t 2 /nobreak >nul

REM [2/2] Start skill-manager frontend
echo [2/2] Starting skill-manager frontend (port %SKILL_WEB_PORT%)...
cd /d "%~dp0..\apps\skill-manager"

REM Kill any existing process on frontend port first
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%SKILL_WEB_PORT% " ^| find "LISTENING" 2^>nul') do (
    echo Killing existing process on port %SKILL_WEB_PORT% - PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Check node_modules
if not exist "node_modules" (
    echo Installing dependencies...
    cd /d "%~dp0.."
    pnpm install
    cd /d "%~dp0..\apps\skill-manager"
)

REM Start skill-manager frontend service
start "skill-manager-frontend" cmd /k "pnpm dev"

echo.
echo ========================================
echo   Skill Manager Services Started!
echo ========================================
echo.
echo Service URLs:
echo   * Skill Manager frontend: http://localhost:%SKILL_WEB_PORT%/skills
echo   * Skill Manager backend:  http://localhost:%SKILL_API_PORT%/api/health
echo   * Admin password: 仅本地开发占位（可用环境变量 SKILL_MANAGER_ADMIN_PASSWORD 覆盖）
echo.
goto :eof

:error
echo.
echo Startup aborted due to configuration error above.
pause
exit /b 1
