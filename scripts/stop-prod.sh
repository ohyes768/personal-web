#!/bin/bash
# 生产环境停止脚本

set -e

# 颜色定义
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${RED}[INFO]${NC} $1"
}

log_info "停止生产环境服务..."

if docker compose version &> /dev/null; then
    docker compose -f docker-compose.prod.yml down
else
    docker-compose -f docker-compose.prod.yml down
fi

log_info "服务已停止"
