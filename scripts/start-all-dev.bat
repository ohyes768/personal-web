@echo off
REM ============================================
REM personal-web 本地开发环境 - 一键启动
REM 启动 Gateway、Frontend、douyin-processor
REM ============================================

setlocal enabledelayedexpansion

REM 颜色设置
set GREEN=[92m
set YELLOW=[93m
set RED=[91m
set BLUE=[94m
set RESET=[0m

echo %BLUE%========================================%RESET%
echo %BLUE%  personal-web 本地开发环境启动%RESET%
echo %BLUE%========================================%RESET%
echo.

REM 检查必要的环境
echo %YELLOW%[1/5] 检查开发环境...%RESET%

where python >nul 2>nul
if errorlevel 1 (
    echo %RED%错误: 未找到 Python，请先安装 Python%RESET%
    pause
    exit /b 1
)

where node >nul 2>nul
if errorlevel 2>nul (
    echo %RED%错误: 未找到 Node.js，请先安装 Node.js%RESET%
    pause
    exit /b 1
)

where uv >nul 2>nul
if errorlevel 1 (
    echo %YELLOW%警告: 未找到 uv，尝试使用 pip...%RESET%
    set USE_UV=0
) else (
    set USE_UV=1
)
echo %GREEN%✓ 环境检查完成%RESET%
echo.

REM 1. 启动 douyin-processor
echo %YELLOW%[2/5] 启动 douyin-processor...%RESET%
cd /d "%~dp0..\backend\douyin-processor"

REM 检查 .env 文件
if not exist ".env" (
    echo %YELLOW%创建 .env 文件...%RESET%
    copy .env.example .env >nul
    echo %YELLOW%警告: 请配置 backend\douyin-processor\.env 中的 ALIYUN_ACCESS_KEY%RESET%
)

REM 检查虚拟环境
if not exist ".venv" (
    echo %YELLOW%创建虚拟环境...%RESET%
    if "!USE_UV!"=="1" (
        uv venv .venv
        uv sync
    ) else (
        echo %RED%错误: douyin-processor 需要 uv 包管理器%RESET%
        echo %YELLOW%请安装: pip install uv%RESET%
        pause
        exit /b 1
    )
)

REM 启动 douyin-processor（新窗口）
echo %GREEN%✓ 启动 douyin-processor (端口 8093)%RESET%
start "douyin-processor" cmd /k ".venv\Scripts\activate && python main.py"

cd /d "%~dp0"
timeout /t 2 /nobreak >nul

REM 2. 启动 Gateway
echo %YELLOW%[3/5] 启动 Gateway...%RESET%
cd /d "%~dp0..\gateway"

REM 检查虚拟环境
if not exist ".venv" (
    echo %YELLOW%创建虚拟环境...%RESET%
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
)

REM 检查 .env 文件
if not exist ".env" (
    echo %YELLOW%创建 .env 文件...%RESET%
    copy .env.example .env
    REM 配置指向本地 douyin-processor
    echo DOUYIN_SERVICE_URL=http://localhost:8093 >> .env
    echo DOUYIN_PROCESSOR_URL=http://localhost:8093 >> .env
    echo HOST=0.0.0.0 >> .env
    echo PORT=8070 >> .env
    echo LOG_LEVEL=DEBUG >> .env
    echo REQUEST_TIMEOUT=300.0 >> .env
    echo CORS_ORIGINS=["http://localhost:3000"] >> .env
)

REM 启动 Gateway（新窗口）
echo %GREEN%✓ 启动 Gateway (端口 8070)%RESET%
start "Gateway" cmd /k ".venv\Scripts\activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8070"

cd /d "%~dp0"
timeout /t 2 /nobreak >nul

REM 3. 启动 Frontend
echo %YELLOW%[4/5] 启动 Frontend...%RESET%
cd /d "%~dp0..\frontend"

REM 检查 node_modules
if not exist "node_modules" (
    echo %YELLOW%安装前端依赖...%RESET%
    npm install
)

REM 检查 .env.local
if not exist ".env.local" (
    echo %YELLOW%创建 .env.local 文件...%RESET%
    echo NEXT_PUBLIC_API_BASE_URL=http://localhost:8070 > .env.local
)

REM 启动 Frontend（新窗口）
echo %GREEN%✓ 启动 Frontend (端口 3000)%RESET%
start "Frontend" cmd /k "npm run dev"

cd /d "%~dp0"
timeout /t 3 /nobreak >nul

REM 4. 等待服务启动并检查
echo %YELLOW%[5/5] 等待服务启动...%RESET%
echo.
timeout /t 5 /nobreak >nul

REM 检查服务状态
echo %BLUE%========================================%RESET%
echo %BLUE%  服务状态检查%RESET%
echo %BLUE%========================================%RESET%

REM 检查 douyin-processor
curl -s http://localhost:8093/health >nul 2>nul
if errorlevel 1 (
    echo %RED%✗ douyin-processor (8093) - 未响应%RESET%
) else (
    echo %GREEN%✓ douyin-processor (8093) - 运行正常%RESET%
)

REM 检查 Gateway
curl -s http://localhost:8070/api/health >nul 2>nul
if errorlevel 1 (
    echo %RED%✗ Gateway (8070) - 未响应%RESET%
) else (
    echo %GREEN%✓ Gateway (8070) - 运行正常%RESET%
)

REM 检查 Frontend
curl -s http://localhost:3000 >nul 2>nul
if errorlevel 1 (
    echo %YELLOW%⏳ Frontend (3000) - 启动中...%RESET%
) else (
    echo %GREEN%✓ Frontend (3000) - 运行正常%RESET%
)

echo.
echo %GREEN%========================================%RESET%
echo %GREEN%  所有服务已启动！%RESET%
echo %GREEN%========================================%RESET%
echo.
echo %BLUE%服务访问地址:%RESET%
echo   - Frontend:      %BLUE%http://localhost:3000%RESET%
echo   - Gateway API:   %BLUE%http://localhost:8070%RESET%
echo   - Gateway 文档:  %BLUE%http://localhost:8070/docs%RESET%
echo   - douyin-proc:   %BLUE%http://localhost:8093%RESET%
echo.
echo %YELLOW%提示: 关闭此窗口不会停止服务，请关闭各自的服务窗口%RESET%
echo.
pause
