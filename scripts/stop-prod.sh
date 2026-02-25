#!/bin/bash
# 生产环境停止脚本
# 用法: ./scripts/stop-prod.sh

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo ""
echo -e "${YELLOW}=========================================${NC}"
echo -e "${YELLOW}  停止生产环境服务${NC}"
echo -e "${YELLOW}=========================================${NC}"
echo ""

# 确定使用哪个命令
if docker compose version &> /dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# 停止服务
log_info "停止生产环境服务..."
$DOCKER_COMPOSE -f docker-compose.yml down

log_info "生产环境服务已停止"
echo ""
echo -e "${GREEN}提示:${NC}"
echo -e "  数据卷已保留，重新启动不会丢失数据"
echo -e "  如需清理数据卷，请运行: ${YELLOW}docker volume rm personal-web_douying-data personal-web_douying-cache personal-web_douying-logs${NC}"
echo ""
