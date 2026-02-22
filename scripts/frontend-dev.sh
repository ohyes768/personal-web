#!/bin/bash
# Frontend 开发环境启动脚本

cd "$(dirname "$0")/.."

echo "======================================"
echo "Frontend 开发环境启动"
echo "======================================"

# 进入 frontend 目录
cd frontend

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "📦 安装依赖..."
    pnpm install
    echo "✅ 依赖安装完成"
fi

# 创建日志目录
mkdir -p ../scripts/logs

# 启动开发服务器
echo "🚀 启动 Frontend 服务..."
echo "📍 访问地址: http://localhost:3000"
echo "======================================"

pnpm dev
