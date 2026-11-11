@echo off
REM service-manager 本地开发启动（前端 3012 + 后端 8102）
REM 用法：先复制本文件旁的 .env.local.example 为 .env.local 填入口令，再双击运行。
REM 后端走本机 Docker socket（直连比 socket-proxy 省一层），前端 dev rewrite 代理到 8102。

setlocal
cd /d "%~dp0.."

if not exist "backend\service-manager\.env.local" (
    echo [错误] 缺少 backend\service-manager\.env.local
    echo         请复制 .env.local.example 为 .env.local 并填写 SERVICE_MANAGER_ADMIN_PASSWORD 等值。
    exit /b 1
)

echo === 启动 service-manager 后端（http://127.0.0.1:8102）===
start "service-manager-backend" cmd /k "cd /d %CD%\backend\service-manager && set SERVICE_MANAGER_DOCKER_HOST=unix:///var/run/docker.sock && ..\..\backend\service-manager\.venv\Scripts\python -m uvicorn src.main:app --host 127.0.0.1 --port 8102 --reload"

echo === 启动 service-manager 前端（http://127.0.0.1:3012/services）===
start "service-manager-frontend" cmd /k "cd /d %CD%\apps\service-manager && pnpm dev"

echo.
echo 打开 http://127.0.0.1:3012/services ，口令见 backend\service-manager\.env.local
endlocal
