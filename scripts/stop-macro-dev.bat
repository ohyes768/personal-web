@echo off
REM ============================================
REM personal-web Local Development - Stop
REM ============================================

echo.
echo ========================================
echo   Stopping Dev Environment
echo ========================================
echo.

echo Stopping services...

REM Run PowerShell script
powershell -ExecutionPolicy Bypass -File "%~dp0stop-services.ps1"

timeout /t 2 /nobreak >nul

REM Fallback: kill by port
echo Force checking ports...
for %%p in (8094 3000) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| find ":%%p " ^| find "LISTENING" 2^>nul') do (
        if "%%a" neq "" taskkill /F /PID %%a >nul 2>&1
    )
)

REM Clear Python cache to ensure fresh reload
echo.
echo Clearing Python cache...
cd /d "%~dp0..\backend\global-macro-fin"
if exist "src\__pycache__" rmdir /s /q "src\__pycache__"
if exist "src\api\__pycache__" rmdir /s /q "src\api\__pycache__"
if exist "src\services\__pycache__" rmdir /s /q "src\services\__pycache__"
if exist "src\utils\__pycache__" rmdir /s /q "src\utils\__pycache__"
if exist ".venv\Lib\site-packages\src*.pyc" del /f /q ".venv\Lib\site-packages\src*.pyc" 2>nul
echo Cache cleared.

echo.
echo All services stopped.
echo.
pause
