#!/bin/bash
# Gateway 开发环境启动脚本

cd "$(dirname "$0")/.."

echo "======================================"
echo "Gateway 开发环境启动"
echo "======================================"

# 进入 gateway 目录
cd gateway

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "⚠️  警告: .env 文件不存在，使用 .env.example 创建"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ 已创建 .env 文件"
    else
        echo "❌ 错误: .env.example 文件也不存在"
        exit 1
    fi
fi

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "📦 创建 Python 虚拟环境..."
    python -m venv .venv
    echo "✅ 虚拟环境创建完成"
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source .venv/bin/activate

# 安装依赖
echo "📥 安装/更新依赖..."
pip install -r requirements.txt --quiet

# 创建日志目录
mkdir -p ../scripts/logs

# 启动服务
echo "🚀 启动 Gateway 服务..."
echo "📍 API 文档: http://localhost:8080/docs"
echo "📍 健康检查: http://localhost:8080/api/health"
echo "======================================"

uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
