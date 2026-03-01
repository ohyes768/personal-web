@echo off
REM ============================================
REM personal-web 本地开发环境 - 一键停止
REM 停止 Gateway、Frontend、douyin-processor
REM ============================================

setlocal enabledelayedexpansion

REM 颜色设置
set GREEN=[92m
set YELLOW=[93m
set RED=[91m
set BLUE=[94m
set RESET=[0m

echo %BLUE%========================================%RESET%
echo %BLUE%  停止 personal-web 开发环境%RESET%
echo %BLUE%========================================%RESET%
echo.

echo %YELLOW%正在查找并停止服务进程...%RESET%
echo.

REM 查找并停止 uvicorn 进程 (Gateway 和 douyin-processor)
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "python.exe"') do (
    taskkill /F /PID %%a 2>nul
)

REM 查找并停止 node 进程 (Frontend)
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "node.exe"') do (
    taskkill /F /PID %%a 2>nul
)

timeout /t 2 /nobreak >nul

echo %GREEN%========================================%RESET%
echo %GREEN%  所有服务已停止%RESET%
echo %GREEN%========================================%RESET%
echo.
pause
