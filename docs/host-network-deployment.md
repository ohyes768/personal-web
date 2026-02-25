# Host 网络模式部署指南

本文档说明如何使用 host 网络模式部署 Gateway，使其可以直接访问宿主机上运行的 douying-collect 服务。

## 为什么使用 host 网络模式？

### 优点
- ✅ **直接访问宿主机服务** - Gateway 可以通过 `localhost:8093` 访问 douying-collect
- ✅ **无需配置复杂的网络** - 不需要考虑 Docker 网络互通问题
- ✅ **性能更好** - 减少 NAT 转换，降低延迟
- ✅ **配置简单** - `DOUYIN_SERVICE_URL=http://localhost:8093`

### 缺点
- ⚠️ **端口冲突风险** - Gateway 占用宿主机 8080 端口
- ⚠️ **安全性稍低** - 容器直接连接到宿主机网络

## 网络架构

```
服务器 (宿主机)
├── douying-collect (独立运行)
│   └── 监听: localhost:8093
│
├── api-gateway (host 网络模式)
│   ├── 直接访问宿主机网络
│   ├── 访问 douying-collect: http://localhost:8093 ✅
│   └── 对外端口: 8080
│
└── personal-web-frontend (bridge 网络模式)
    ├── Docker 内部网络
    ├── 访问 Gateway: http://服务器IP:8080
    └── 端口映射: 3000:3000
```

## 配置说明

### docker-compose.yml

```yaml
services:
  gateway:
    network_mode: host  # 关键配置：使用宿主机网络
    environment:
      - PORT=8080
    # 不需要 ports 配置（host 模式直接使用宿主机端口）
  
  frontend:
    networks:
      - web-network
    ports:
      - "3000:3000"
    environment:
      # Frontend 通过服务器 IP 访问 Gateway
      - NEXT_PUBLIC_API_BASE_URL=http://服务器IP:8080
```

### gateway/.env

```bash
# Gateway 使用 host 网络，可以直接访问 localhost
DOUYIN_SERVICE_URL=http://localhost:8093
```

## 部署步骤

### 自动部署（推荐）

```bash
cd /root/personal-web
chmod +x scripts/deploy-host-network.sh
./scripts/deploy-host-network.sh
```

脚本会自动：
1. 检查 douying-collect 是否运行
2. 测试 localhost:8093 可访问性
3. 获取服务器 IP
4. 自动配置环境变量
5. 检查并处理端口冲突
6. 构建并启动服务
7. 验证服务健康状态

### 手动部署

```bash
# 1. 确保 douying-collect 正在运行
docker ps | grep douying-collect

# 2. 测试 douying-collect 可访问
curl http://localhost:8093/api/health

# 3. 获取服务器 IP
hostname -I | awk '{print $1}'

# 4. 配置环境变量
cat > gateway/.env << 'EOF'
DOUYIN_SERVICE_URL=http://localhost:8093
HOST=0.0.0.0
PORT=8080
LOG_LEVEL=INFO
REQUEST_TIMEOUT=300.0
CORS_ORIGINS=["http://localhost:3000","http://服务器IP:3000"]
