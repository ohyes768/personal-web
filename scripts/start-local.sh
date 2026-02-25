#!/bin/bash
# 本地开发环境启动脚本
# 用法: ./scripts/start-local.sh

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo ""
echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}  启动本地开发环境${NC}"
echo -e "${BLUE}=========================================${NC}"
echo ""

# 检查 docker-compose.local.yml 是否存在
if [ ! -f "docker-compose.local.yml" ]; then
    log_warn "docker-compose.local.yml 不存在，将使用默认配置"
    log_warn "如需自定义本地开发配置，请创建 docker-compose.local.yml"
fi

# 准备本地环境变量
if [ ! -f "gateway/.env.local" ]; then
    if [ -f "gateway/.env.example" ]; then
        log_warn "gateway/.env.local 不存在，从 .env.example 复制"
        cp gateway/.env.example gateway/.env.local
        log_warn "请根据需要编辑 gateway/.env.local"
        log_warn "注意: 本地开发时，DOUYIN_SERVICE_URL 应配置为:"
        log_warn "  http://host.docker.internal:8093  (如果服务在宿主机)"
        log_warn "  http://douying-collect:8093      (如果服务在 Docker 中)"
    fi
fi

# 确定使用哪个命令
if docker compose version &> /dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# 启动服务
log_info "启动本地开发服务..."

if [ -f "docker-compose.local.yml" ]; then
    $DOCKER_COMPOSE -f docker-compose.local.yml up -d --build
else
    log_warn "使用 docker-compose.yml 启动（开发模式）"
    $DOCKER_COMPOSE -f docker-compose.yml up -d --build
fi

log_info "等待服务启动..."
sleep 5

log_info "本地开发环境已启动"
echo ""
echo -e "${GREEN}服务访问地址:${NC}"
echo -e "  - Frontend:  ${BLUE}http://localhost:3000${NC}"
echo -e "  - Gateway:   ${BLUE}http://localhost:8080${NC}"
echo -e "  - API文档:   ${BLUE}http://localhost:8080/docs${NC}"
echo ""
echo -e "${YELLOW}开发提示:${NC}"
echo -e "  - 代码修改后会自动重载"
echo -e "  - 查看日志: ${BLUE}docker compose -f docker-compose.local.yml logs -f${NC}"
echo -e "  - 停止服务: ${BLUE}./scripts/stop-local.sh${NC}"
echo ""
