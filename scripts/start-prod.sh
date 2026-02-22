#!/bin/bash
# 生产环境启动脚本

set -e

# 颜色定义
GREEN='\033[0;32m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_info "启动生产环境服务..."

if docker compose version &> /dev/null; then
    docker compose -f docker-compose.prod.yml up -d
else
    docker-compose -f docker-compose.prod.yml up -d
fi

log_info "服务启动中，请稍候..."
sleep 5

log_info "服务已启动"
echo ""
echo "访问地址:"
echo "  - Frontend:  http://localhost:3000"
echo "  - Gateway:   http://localhost:8080"
echo "  - API文档:   http://localhost:8080/docs"
