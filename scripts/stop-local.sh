#!/bin/bash
# 本地开发环境停止脚本
# 用法: ./scripts/stop-local.sh

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${RED}[WARN]${NC} $1"
}

echo ""
echo "停止本地开发环境..."
echo ""

# 确定使用哪个命令
if docker compose version &> /dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# 停止服务
if [ -f "docker-compose.local.yml" ]; then
    $DOCKER_COMPOSE -f docker-compose.local.yml down
    log_info "本地开发服务已停止 (docker-compose.local.yml)"
else
    $DOCKER_COMPOSE -f docker-compose.yml down
    log_info "开发服务已停止 (docker-compose.yml)"
fi

echo ""
