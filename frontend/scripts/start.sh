#!/bin/bash
# 前端启动脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR" || exit 1

echo "=========================================="
echo "启动 Frontend 开发服务器"
echo "=========================================="

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "node_modules 不存在，正在安装依赖..."
    npm install
fi

# 检查 .env.local
if [ ! -f ".env.local" ]; then
    echo "警告: .env.local 不存在，创建默认配置..."
    cat > .env.local << EOF
NEXT_PUBLIC_API_BASE_URL=http://localhost:8094
EOF
fi

# 启动开发服务器
echo "启动 Next.js 开发服务器..."
npm run dev
