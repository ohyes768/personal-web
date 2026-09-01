@echo off
echo.
echo ========================================
echo   Stopping Fund-Select Dev Environment
echo ========================================
echo.

for %%p in (8095 3005) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| find ":%%p " ^| find "LISTENING" 2^>nul') do (
        echo Killing process on port %%p - PID %%a
        taskkill /F /T /PID %%a >nul 2>&1
    )
)

echo.
echo Fund-Select dev environment stopped.
echo.
pause
