#!/bin/bash
# 使用 host 网络模式部署 Gateway
# Gateway 可以直接访问宿主机上的 douying-collect

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo ""
echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}  部署 Gateway (host 网络模式)${NC}"
echo -e "${BLUE}=========================================${NC}"
echo ""

# 1. 检查 douying-collect 是否运行
log_info "检查 douying-collect 服务..."
if docker ps | grep -q douying-collect; then
    log_info "✓ douying-collect 正在运行"
    DOUYYIN_PORT=$(docker port douying-collect 8093 2>/dev/null | head -1)
    if [ -n "$DOUYYIN_PORT" ]; then
        echo "   端口映射: $DOUYYIN_PORT"
    fi
else
    log_error "✗ douying-collect 未运行"
    echo "   请先启动 douying-collect 服务"
    exit 1
fi

# 2. 测试 localhost:8093 是否可访问
log_info "测试 douying-collect 健康检查..."
if curl -f -s http://localhost:8093/api/health > /dev/null 2>&1; then
    log_info "✓ douying-collect 响应正常"
else
    log_warn "✗ douying-collect 可能未完全启动，请稍候"
fi

# 3. 获取服务器 IP
log_info "获取服务器网络信息..."
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "   主网卡 IP: $SERVER_IP"

# 4. 更新 frontend 环境变量（使用服务器实际 IP）
log_info "配置 Frontend 环境变量..."
if [ -f "docker-compose.yml" ]; then
    # 更新 NEXT_PUBLIC_API_BASE_URL
    sed -i "s|NEXT_PUBLIC_API_BASE_URL=http://.*:8080|NEXT_PUBLIC_API_BASE_URL=http://$SERVER_IP:8080|g" docker-compose.yml
    log_info "已配置 NEXT_PUBLIC_API_BASE_URL=http://$SERVER_IP:8080"
fi

# 5. 更新 CORS 配置
if [ -f "gateway/.env" ]; then
    sed -i "s|CORS_ORIGINS=\".*\"|CORS_ORIGINS=[\"http://localhost:3000\",\"http://$SERVER_IP:3000\"]|g" gateway/.env
    log_info "已配置 CORS_ORIGINS"
fi

# 6. 检查端口占用
log_info "检查端口占用..."
if netstat -tulpn 2>/dev/null | grep -q ":8080 "; then
    log_warn "端口 8080 已被占用"
    NETSTAT_PID=$(netstat -tulpn 2>/dev/null | grep ":8080 " | awk '{print $7}' | cut -d'/' -f1)
    echo "   占用进程 PID: $NETSTAT_PID"
    
    if [ -n "$NETSTAT_PID" ] && [ "$NETSTAT_PID" != "-" ]; then
        read -p "是否停止占用端口的进程？(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill $NETSTAT_PID 2>/dev/null || true
            sleep 2
            log_info "已停止进程 $NETSTAT_PID"
        else
            log_error "端口冲突，无法启动"
            exit 1
        fi
    fi
fi

# 7. 停止旧容器（如果存在）
if docker ps -a | grep -q api-gateway; then
    log_info "停止旧的 Gateway 容器..."
    docker stop api-gateway 2>/dev/null || true
    docker rm api-gateway 2>/dev/null || true
fi

if docker ps -a | grep -q personal-web-frontend; then
    log_info "停止旧的 Frontend 容器..."
    docker stop personal-web-frontend 2>/dev/null || true
    docker rm personal-web-frontend 2>/dev/null || true
fi

# 8. 构建并启动服务
log_info "构建并启动服务..."
docker compose -f docker-compose.yml up -d --build

# 9. 等待服务启动
log_info "等待服务启动..."
sleep 20

# 10. 健康检查
log_info "检查服务健康状态..."

# 检查 Gateway
if curl -f -s http://localhost:8080/api/health > /dev/null 2>&1; then
    log_info "✓ Gateway 服务正常"
else
    log_warn "✗ Gateway 服务未响应，请检查日志"
    echo "   查看日志: docker logs api-gateway"
fi

# 检查 Frontend
if curl -f -s http://localhost:3000 > /dev/null 2>&1; then
    log_info "✓ Frontend 服务正常"
else
    log_warn "✗ Frontend 服务未响应，请检查日志"
    echo "   查看日志: docker logs personal-web-frontend"
fi

# 11. 测试完整链路
log_info "测试完整链路..."
log_info "Frontend → Gateway → douying-collect"

# 测试 Gateway → douying-collect
if docker exec api-gateway curl -f -s http://localhost:8093/api/health > /dev/null 2>&1; then
    log_info "✓ Gateway 可以访问 douying-collect"
else
    log_warn "✗ Gateway 无法访问 douying-collect"
fi

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${GREEN}服务访问地址:${NC}"
echo -e "  - Frontend:      ${BLUE}http://$SERVER_IP:3000${NC}"
echo -e "  - Gateway:       ${BLUE}http://$SERVER_IP:8080${NC}"
echo -e "  - API 文档:      ${BLUE}http://$SERVER_IP:8080/docs${NC}"
echo -e "  - 抖音视频 API:  ${BLUE}http://$SERVER_IP:8080/api/douyin/videos${NC}"
echo ""
echo -e "${YELLOW}已部署的服务:${NC}"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAMES|douying|gateway|frontend"
echo ""
echo -e "${YELLOW}常用命令:${NC}"
echo -e "  查看 Gateway 日志:    ${BLUE}docker logs api-gateway -f${NC}"
echo -e "  查看 Frontend 日志:   ${BLUE}docker logs personal-web-frontend -f${NC}"
echo -e "  重启 Gateway:         ${BLUE}docker restart api-gateway${NC}"
echo -e "  停止服务:             ${BLUE}docker compose -f docker-compose.yml down${NC}"
echo ""
echo -e "${YELLOW}网络模式:${NC}"
echo -e "  - Gateway:  ${BLUE}host 网络${NC} (直接访问宿主机服务)"
echo -e "  - Frontend: ${BLUE}bridge 网络${NC} (端口映射 3000:3000)"
echo ""
