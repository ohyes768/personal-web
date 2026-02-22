#!/bin/bash
# Docker 部署脚本 - 用于阿里云 ECS
# 用法: ./scripts/deploy.sh [环境]
# 示例: ./scripts/deploy.sh production

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# 检查 Docker 和 Docker Compose
check_dependencies() {
    log_info "检查依赖..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi
    
    log_info "依赖检查通过"
}

# 准备环境变量
prepare_env() {
    log_info "准备环境变量..."
    
    # Gateway 环境变量
    if [ ! -f "gateway/.env" ]; then
        if [ -f "gateway/.env.example" ]; then
            log_warn "gateway/.env 不存在，从 .env.example 复制"
            cp gateway/.env.example gateway/.env
            log_warn "请编辑 gateway/.env 配置必要的环境变量"
        else
            log_error "gateway/.env 和 gateway/.env.example 都不存在"
            exit 1
        fi
    fi
    
    log_info "环境变量准备完成"
}

# 构建镜像
build_images() {
    log_info "开始构建 Docker 镜像..."
    
    # 使用 docker compose 或 docker-compose
    if docker compose version &> /dev/null; then
        docker compose -f docker-compose.prod.yml build --no-cache
    else
        docker-compose -f docker-compose.prod.yml build --no-cache
    fi
    
    log_info "镜像构建完成"
}

# 启动服务
start_services() {
    log_info "启动服务..."
    
    # 使用 docker compose 或 docker-compose
    if docker compose version &> /dev/null; then
        docker compose -f docker-compose.prod.yml up -d
    else
        docker-compose -f docker-compose.prod.yml up -d
    fi
    
    log_info "服务启动完成"
}

# 检查服务健康状态
check_health() {
    log_info "等待服务启动..."
    sleep 10
    
    log_info "检查服务健康状态..."
    
    # 检查 Gateway
    if curl -f -s http://localhost:8080/api/health > /dev/null; then
        log_info "✓ Gateway 服务正常"
    else
        log_warn "✗ Gateway 服务未响应"
    fi
    
    # 检查 Frontend
    if curl -f -s http://localhost:3000 > /dev/null; then
        log_info "✓ Frontend 服务正常"
    else
        log_warn "✗ Frontend 服务未响应"
    fi
    
    # 检查 Douying-Collect
    if curl -f -s http://localhost:8093/api/health > /dev/null; then
        log_info "✓ Douying-Collect 服务正常"
    else
        log_warn "✗ Douying-Collect 服务未响应"
    fi
}

# 显示日志
show_logs() {
    log_info "查看服务日志（按 Ctrl+C 退出）..."
    
    if docker compose version &> /dev/null; then
        docker compose -f docker-compose.prod.yml logs -f
    else
        docker-compose -f docker-compose.prod.yml logs -f
    fi
}

# 主函数
main() {
    log_info "========================================="
    log_info "Personal Web Docker 部署脚本"
    log_info "========================================="
    
    check_dependencies
    prepare_env
    build_images
    start_services
    check_health
    
    echo ""
    log_info "========================================="
    log_info "部署完成！"
    log_info "========================================="
    log_info "Frontend:  http://localhost:3000"
    log_info "Gateway:   http://localhost:8080"
    log_info "API文档:   http://localhost:8080/docs"
    log_info ""
    log_info "查看日志: ./scripts/deploy.sh logs"
    log_info "停止服务: docker compose -f docker-compose.prod.yml down"
    log_info "========================================="
}

# 如果传入 logs 参数，显示日志
if [ "$1" = "logs" ]; then
    show_logs
else
    main
fi
