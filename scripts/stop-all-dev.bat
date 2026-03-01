@echo off
REM ============================================
REM personal-web Local Development - Stop All
REM Stop Gateway, Frontend, douyin-processor
REM ============================================

echo.
echo ========================================
echo   Stop personal-web Dev Environment
echo ========================================
echo.

echo Stopping all services...
echo.

REM Stop Python processes (Gateway and douyin-processor)
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "python.exe"') do (
    taskkill /F /PID %%a 2>nul
)

REM Stop Node processes (Frontend)
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "node.exe"') do (
    taskkill /F /PID %%a 2>nul
)

timeout /t 2 /nobreak >nul

echo ========================================
echo   All Services Stopped
echo ========================================
echo.
pause
