# 部署脚本使用说明

本目录包含项目的部署和运维脚本。

## 脚本列表

### 生产环境（线上 ECS）

#### deploy.sh
**用途**: 生产环境一键部署脚本

**功能**:
- 自动检查 Docker 和 Docker Compose 依赖
- 准备环境变量
- 检查和创建 Docker 网络
- 构建所有服务镜像
- 启动所有服务
- 健康检查
- 显示服务状态

**用法**:
```bash
# 完整部署（构建+启动）
./scripts/deploy.sh

# 查看服务日志
./scripts/deploy.sh logs

# 查看服务状态
./scripts/deploy.sh status

# 重启服务
./scripts/deploy.sh restart
```

**配置文件**: `docker-compose.yml`

#### stop-prod.sh
**用途**: 停止生产环境服务

**用法**:
```bash
./scripts/stop-prod.sh
```

**注意**: 停止服务不会删除数据卷，数据会保留。

### 本地开发环境

#### start-local.sh
**用途**: 启动本地开发环境

**功能**:
- 检查本地开发配置文件
- 自动准备 .env.local
- 启动开发服务（支持热重载）

**用法**:
```bash
./scripts/start-local.sh
```

**配置文件**: `docker-compose.local.yml`（如果存在）

**注意**: 
- 代码修改后会自动重载
- 适用于本地开发和调试

#### stop-local.sh
**用途**: 停止本地开发环境

**用法**:
```bash
./scripts/stop-local.sh
```

### Windows 本地开发

#### frontend-dev.bat
**用途**: Windows 环境启动前端开发服务器

**用法**:
```bash
scripts\frontend-dev.bat
```

**功能**:
- 自动检测 pnpm/npm
- 安装依赖（如果需要）
- 启动 Next.js 开发服务器

#### gateway-dev.bat
**用途**: Windows 环境启动 Gateway 开发服务器

**用法**:
```bash
scripts\gateway-dev.bat
```

**功能**:
- 自动创建和配置 Python 虚拟环境
- 安装依赖
- 启动 Uvicorn 开发服务器

#### *-dev.sh
**用途**: Linux/Mac 环境的对应脚本

**用法**:
```bash
./scripts/frontend-dev.sh
./scripts/gateway-dev.sh
```

## 环境配置

### 生产环境 (.env)

**gateway/.env**:
```bash
# 后端服务地址（使用 Docker 服务名）
DOUYIN_SERVICE_URL=http://douying-collect:8093
FINANCIAL_SERVICE_URL=http://financial-dashboard:8091
NEWS_SERVICE_URL=http://xwlb-analyze:8092

# Gateway 配置
HOST=0.0.0.0
PORT=8080
LOG_LEVEL=INFO
REQUEST_TIMEOUT=300.0

# CORS 配置
CORS_ORIGINS=["http://your-server-ip:3000","http://your-domain.com"]
```

### 本地开发 (.env.local)

**gateway/.env.local**:
```bash
# 本地开发时访问宿主机上的服务
DOUYIN_SERVICE_URL=http://host.docker.internal:8093

# 或如果服务也在 Docker 中运行
# DOUYIN_SERVICE_URL=http://douying-collect:8093

# 其他配置
HOST=0.0.0.0
PORT=8080
LOG_LEVEL=DEBUG
REQUEST_TIMEOUT=300.0

# CORS 配置
CORS_ORIGINS=["http://localhost:3000"]
```

## 常用命令

### 查看日志
```bash
# 生产环境
docker compose -f docker-compose.yml logs -f

# 特定服务
docker compose -f docker-compose.yml logs -f gateway
docker compose -f docker-compose.yml logs -f douying-collect
docker compose -f docker-compose.yml logs -f frontend

# 本地开发
docker compose -f docker-compose.local.yml logs -f
```

### 服务管理
```bash
# 启动所有服务
./scripts/deploy.sh

# 仅启动特定服务
docker compose -f docker-compose.yml up -d gateway

# 重启服务
./scripts/deploy.sh restart

# 停止服务
./scripts/stop-prod.sh
```

### 进入容器调试
```bash
# 进入 Gateway 容器
docker exec -it api-gateway bash

# 进入 douying-collect 容器
docker exec -it douying-collect bash

# 进入 Frontend 容器
docker exec -it personal-web-frontend bash
```

### 验证服务
```bash
# 检查服务健康状态
curl http://localhost:8080/api/health    # Gateway
curl http://localhost:8093/api/health    # Douying-Collect
curl http://localhost:3000               # Frontend

# 测试 Gateway 到后端服务的连通性
docker exec -it api-gateway curl http://douying-collect:8093/api/health
```

## 故障排查

### 1. 服务无法启动

```bash
# 查看详细日志
docker compose -f docker-compose.yml logs

# 检查端口占用
netstat -tulpn | grep :8080
netstat -tulpn | grep :3000
netstat -tulpn | grep :8093
```

### 2. 服务间无法通信

```bash
# 检查网络
docker network ls
docker network inspect web-network

# 确认服务在同一网络
docker network inspect web-network | grep -A 5 "Containers"
```

### 3. 数据卷问题

```bash
# 查看数据卷
docker volume ls | grep personal-web

# 备份数据卷
docker run --rm -v personal-web_douying-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/douying-data-backup.tar.gz /data

# 清理数据卷（谨慎操作）
docker volume rm personal-web_douying-data
```

## 部署流程

### 首次部署到阿里云 ECS

```bash
# 1. 克隆代码到服务器
git clone <your-repo-url> /opt/personal-web
cd /opt/personal-web

# 2. 配置环境变量
cp gateway/.env.example gateway/.env
vim gateway/.env  # 编辑配置

# 3. 执行部署
./scripts/deploy.sh

# 4. 验证服务
curl http://localhost:8080/api/health
curl http://localhost:3000
```

### 更新部署

```bash
# 1. 拉取最新代码
git pull

# 2. 重新构建镜像
docker compose -f docker-compose.yml build --no-cache

# 3. 重启服务
docker compose -f docker-compose.yml up -d

# 或使用部署脚本
./scripts/deploy.sh restart
```

## 目录结构

```
scripts/
├── deploy.sh              # 生产环境部署脚本
├── stop-prod.sh           # 生产环境停止脚本
├── start-local.sh         # 本地开发启动脚本
├── stop-local.sh          # 本地开发停止脚本
├── frontend-dev.bat       # Windows 前端开发脚本
├── frontend-dev.sh        # Linux/Mac 前端开发脚本
├── gateway-dev.bat        # Windows Gateway 开发脚本
├── gateway-dev.sh         # Linux/Mac Gateway 开发脚本
└── README.md              # 本文档
```

## 最佳实践

1. **环境隔离**: 生产环境和本地开发使用不同的配置文件
2. **数据备份**: 定期备份 docker volumes
3. **日志监控**: 使用 `logs -f` 实时查看服务日志
4. **健康检查**: 部署后验证所有服务的健康状态
5. **滚动更新**: 使用 `--no-cache` 重新构建镜像确保更新

## 相关文档

- [部署文件说明](../docs/DEPLOYMENT_FILES.md)
- [快速部署指南](../DOCKER_DEPLOY.md)
- [完整部署文档](../docs/deployment.md)

---

最后更新: 2025-02
