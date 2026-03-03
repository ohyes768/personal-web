#!/bin/bash
# 前端构建脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR" || exit 1

echo "=========================================="
echo "构建 Frontend 生产版本"
echo "=========================================="

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "node_modules 不存在，正在安装依赖..."
    npm install
fi

# 构建
echo "开始构建..."
npm run build

echo "=========================================="
echo "构建完成！"
echo "=========================================="
