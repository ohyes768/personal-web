@echo off
chcp 65001 >nul
cd /d "%~dp0.."
cd frontend

echo ======================================
echo Frontend Development Server
echo ======================================
echo Current directory: %CD%
echo ======================================

REM Detect package manager
where pnpm >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PKG_MANAGER=pnpm
    set DEV_CMD=dev
    goto :found_pm
)

where npm >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PKG_MANAGER=npm
    set DEV_CMD=run dev
    goto :found_pm
)

echo ERROR: No package manager found
echo Please install Node.js first
echo.
echo To install pnpm (recommended):
echo   npm install -g pnpm
pause
exit /b 1

:found_pm
echo Using package manager: %PKG_MANAGER%

if not exist "node_modules" (
    echo Installing dependencies...
    call %PKG_MANAGER% install
)

mkdir ..\scripts\logs 2>nul

echo ======================================
echo Starting Frontend server...
echo URL: http://localhost:3000
echo ======================================
echo.

call %PKG_MANAGER% %DEV_CMD%
