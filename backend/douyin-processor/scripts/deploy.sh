#!/bin/bash
# douyin-processor 部署脚本

set -e

echo "=== douyin-processor 部署脚本 ==="

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "错误: Docker 未安装"
    echo "请先安装 Docker: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# 检查 docker-compose 是否安装
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "错误: docker-compose 未安装"
    echo "请先安装 docker-compose"
    exit 1
fi

# 检查 api-gateway 网络是否存在
NETWORK_NAME="api-gateway_api-network"
if docker network ls | grep -q "$NETWORK_NAME"; then
    echo "✅ 检测到 api-gateway 网络: $NETWORK_NAME"
else
    echo "⚠️  未检测到 api-gateway 网络"
    echo "   请先部署 api-gateway，或使用独立网络模式"
    echo ""
    read -p "是否继续创建独立网络? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "创建独立网络..."
        docker network create app-network
        # 修改 docker-compose.yml 使用独立网络
        sed -i 's/external: true/# external: false/' docker-compose.yml
        sed -i 's/name: api-gateway_api-network/# name: app-network/' docker-compose.yml
    else
        echo "已取消部署"
        exit 0
    fi
fi

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "警告: .env 文件不存在，从 .env.example 复制"
    cp .env.example .env
    echo "请编辑 .env 文件，填入正确的 ALIYUN_ACCESS_KEY"
    exit 1
fi

# 创建数据目录
echo "创建数据目录..."
mkdir -p data/output logs

# 停止旧容器
echo "停止旧容器..."
docker-compose down 2>/dev/null || true

# 构建镜像
echo "构建镜像（已配置国内镜像源）..."
docker-compose build

# 启动服务
echo "启动服务..."
docker-compose up -d

# 等待服务启动
echo "等待服务启动..."
sleep 5

# 检查服务状态
echo "检查服务状态..."
docker-compose ps
docker-compose logs --tail=20

# 健康检查
echo "健康检查..."
if curl -sf http://localhost:8093/health > /dev/null; then
    echo "✅ 服务启动成功!"
    echo ""
    echo "本地访问:"
    echo "  - API 文档: http://localhost:8093/docs"
    echo "  - 健康检查: http://localhost:8093/health"
    echo "  - 处理接口: http://localhost:8093/api/process"
    echo ""
    if docker network ls | grep -q "$NETWORK_NAME"; then
        echo "通过 api-gateway 访问:"
        echo "  - 处理接口: http://localhost:8010/api/douyin/process"
        echo "  - 查询结果: http://localhost:8010/api/douyin/videos/{id}/result"
    fi
else
    echo "❌ 服务启动失败，请检查日志"
    docker-compose logs
fi
