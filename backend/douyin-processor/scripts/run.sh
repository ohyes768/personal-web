#!/bin/bash
# douyin-processor 启动脚本

cd "$(dirname "$0")/.."

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "错误: 虚拟环境不存在，请先运行 scripts/install_deps.sh"
    exit 1
fi

# 启动服务
python main.py
