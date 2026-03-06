#!/bin/bash
# Docker 生产环境部署脚本 - 阿里云 ECS
# 用法：./scripts/deploy.sh [选项]
# 选项:
#   logs     - 查看日志
#   status   - 查看服务状态
#   restart  - 重启服务

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# 检查 Docker 和 Docker Compose
check_dependencies() {
    log_step "检查依赖..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi

    # 确定使用哪个命令
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi

    log_info "依赖检查通过 ($DOCKER_COMPOSE)"
}

# 准备环境变量
prepare_env() {
    log_step "准备环境变量..."
    log_info "环境变量准备完成"
}

# 检查外部网络
check_network() {
    log_step "检查 Docker 网络..."

    if ! $DOCKER_COMPOSE -f docker-compose.yml networks 2>/dev/null | grep -q "web-network"; then
        log_info "创建外部网络 web-network..."
        docker network create web-network 2>/dev/null || true
    else
        log_info "网络 web-network 已存在"
    fi
}

# 构建镜像
build_images() {
    log_step "开始构建 Docker 镜像..."

    $DOCKER_COMPOSE -f docker-compose.yml build --no-cache

    log_info "镜像构建完成"
}

# 启动服务
start_services() {
    log_step "启动服务..."

    $DOCKER_COMPOSE -f docker-compose.yml up -d

    log_info "服务启动完成"
}

# 检查服务健康状态
check_health() {
    log_step "等待服务启动..."
    sleep 10

    log_step "检查服务健康状态..."

    # 检查 douyin-processor
    if curl -f -s http://localhost:8093/health > /dev/null 2>&1; then
        log_info "✓ Douyin-Processor 服务正常"
    else
        log_warn "✗ Douyin-Processor 服务未响应"
    fi

    # 检查 global-macro-fin
    if curl -f -s http://localhost:8094/api/macro/health > /dev/null 2>&1; then
        log_info "✓ Global-Macro-Fin 服务正常"
    else
        log_warn "✗ Global-Macro-Fin 服务未响应"
    fi

    # 检查 Frontend
    if curl -f -s http://localhost:3000 > /dev/null 2>&1; then
        log_info "✓ Frontend 服务正常"
    else
        log_warn "✗ Frontend 服务未响应"
    fi
}

# 显示服务状态
show_status() {
    log_step "服务状态:"
    echo ""
    $DOCKER_COMPOSE -f docker-compose.yml ps
    echo ""

    log_step "容器健康状态:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

# 显示日志
show_logs() {
    log_info "查看服务日志（按 Ctrl+C 退出）..."
    $DOCKER_COMPOSE -f docker-compose.yml logs -f
}

# 重启服务
restart_services() {
    log_step "重启服务..."
    $DOCKER_COMPOSE -f docker-compose.yml restart
    log_info "服务已重启"
    sleep 5
    check_health
}

# 主函数
main() {
    echo ""
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}  Personal Web 生产环境部署脚本${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo ""

    check_dependencies
    prepare_env
    check_network
    build_images
    start_services
    check_health
    show_status

    echo ""
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}  部署完成！${NC}"
    echo -e "${GREEN}=========================================${NC}"
    echo ""
    echo -e "${GREEN}服务访问地址:${NC}"
    echo -e "  - Frontend:       ${BLUE}http://localhost:3000${NC}"
    echo -e "  - Douyin API:     ${BLUE}http://localhost:8093${NC}"
    echo -e "  - Macro API:      ${BLUE}http://localhost:8094${NC}"
    echo ""
    echo -e "${YELLOW}说明：所有服务已通过 Docker 统一部署${NC}"
    echo ""
    echo -e "${YELLOW}常用命令:${NC}"
    echo -e "  查看日志:   ${BLUE}./scripts/deploy.sh logs${NC}"
    echo -e "  查看状态:   ${BLUE}./scripts/deploy.sh status${NC}"
    echo -e "  重启服务:   ${BLUE}./scripts/deploy.sh restart${NC}"
    echo -e "  停止服务:   ${BLUE}docker-compose down${NC}"
    echo ""
}

# 处理命令行参数
case "$1" in
    logs)
        show_logs
        ;;
    status)
        check_dependencies
        show_status
        ;;
    restart)
        check_dependencies
        restart_services
        ;;
    *)
        main
        ;;
esac
