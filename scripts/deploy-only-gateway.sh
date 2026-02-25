#!/bin/bash
# 仅部署 Gateway 和 Frontend（douying-collect 已在运行）
# 用法: ./scripts/deploy-only-gateway.sh

set -e

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
echo -e "${BLUE}  部署 Gateway + Frontend${NC}"
echo -e "${BLUE}  (douying-collect 已在运行)${NC}"
echo -e "${BLUE}=========================================${NC}"
echo ""

# 检查 douying-collect 是否运行
log_info "检查 douying-collect 服务..."
if docker ps | grep -q douying-collect; then
    DOUYYIN_PORT=$(docker port douying-collect 8093 | head -1)
    log_info "✓ douying-collect 正在运行"
    echo "   端口映射: $DOUYYIN_PORT"
else
    log_warn "✗ douying-collect 未运行"
    echo "   请先启动 douying-collect 服务"
    exit 1
fi

# 获取宿主机 IP
log_info "检测宿主机 IP..."
HOST_IP=$(hostname -I | awk '{print $1}')
if [ -z "$HOST_IP" ]; then
    HOST_IP="172.17.0.1"  # Docker 默认网关
fi
echo "   宿主机 IP: $HOST_IP"

# 更新 .env 中的 IP
if [ -f "gateway/.env" ]; then
    log_info "更新 gateway/.env 配置..."
    sed -i "s|DOUYIN_SERVICE_URL=http://.*:8093|DOUYIN_SERVICE_URL=http://$HOST_IP:8093|g" gateway/.env
    log_info "已配置 DOUYIN_SERVICE_URL=http://$HOST_IP:8093"
fi

# 启动服务
log_info "启动 Gateway 和 Frontend..."
docker compose -f docker-compose.yml up -d --build gateway frontend

# 等待服务启动
log_info "等待服务启动..."
sleep 10

# 健康检查
log_info "检查服务健康状态..."

if curl -f -s http://localhost:8080/api/health > /dev/null 2>&1; then
    log_info "✓ Gateway 服务正常"
else
    log_warn "✗ Gateway 服务未响应"
fi

if curl -f -s http://localhost:3000 > /dev/null 2>&1; then
    log_info "✓ Frontend 服务正常"
else
    log_warn "✗ Frontend 服务未响应"
fi

# 测试 Gateway 到 douying-collect 的连通性
log_info "测试 Gateway → douying-collect 连通性..."
if docker exec api-gateway curl -f -s http://$HOST_IP:8093/api/health > /dev/null 2>&1; then
    log_info "✓ Gateway 可以访问 douying-collect"
else
    log_warn "✗ Gateway 无法访问 douying-collect"
    echo "   请检查 gateway/.env 中的 DOUYIN_SERVICE_URL 配置"
fi

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${GREEN}服务访问地址:${NC}"
echo -e "  - Frontend:      ${BLUE}http://localhost:3000${NC}"
echo -e "  - Gateway:       ${BLUE}http://localhost:8080${NC}"
echo -e "  - API 文档:      ${BLUE}http://localhost:8080/docs${NC}"
echo -e "  - Douyin API:    ${BLUE}http://localhost:8080/api/douyin/videos${NC}"
echo ""
echo -e "${YELLOW}已运行的服务:${NC}"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAMES|douying|api-gateway|personal-web"
echo ""
echo -e "${YELLOW}常用命令:${NC}"
echo -e "  查看日志:   ${BLUE}docker compose -f docker-compose.yml logs -f${NC}"
echo -e "  查看状态:   ${BLUE}docker ps${NC}"
echo -e "  重启服务:   ${BLUE}docker compose -f docker-compose.yml restart${NC}"
echo -e "  停止服务:   ${BLUE}docker compose -f docker-compose.yml down${NC}"
echo ""
