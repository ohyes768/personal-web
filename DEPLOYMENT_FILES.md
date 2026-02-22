# Docker 部署文件清单

本文档列出了所有用于阿里云 ECS 部署的 Docker 相关文件。

## 核心配置文件

### 1. docker-compose.prod.yml
生产环境 Docker Compose 配置文件。

**位置**: `/docker-compose.prod.yml`

**服务定义**:
- `gateway`: API 网关服务 (FastAPI)
- `douying-collect`: 抖音数据采集服务
- `frontend`: Next.js 前端应用

**数据卷**:
- `douying-data`: 采集的视频数据
- `douying-cache`: 处理缓存
- `douying-logs`: 应用日志

### 2. nginx/nginx.conf
Nginx 反向代理配置文件。

**位置**: `/nginx/nginx.conf`

**功能**:
- 反向代理前端和 API 服务
- Gzip 压缩
- 静态资源缓存
- 健康检查端点

### 3. Dockerfiles

#### gateway/Dockerfile
FastAPI Gateway 服务镜像。

**基础镜像**: `python:3.11-slim`
**端口**: 8080

#### frontend/Dockerfile  
Next.js 前端应用镜像。

**基础镜像**: `node:20-alpine`
**构建模式**: standalone
**端口**: 3000

#### douying-collect/Dockerfile
抖音数据采集服务镜像。

**基础镜像**: `python:3.12-slim`
**依赖**: Playwright + FFmpeg
**端口**: 8093

### 4. .dockerignore 文件

优化 Docker 构建性能，排除不必要的文件。

- `frontend/.dockerignore`
- `gateway/.dockerignore`

## 部署脚本

### 1. scripts/deploy.sh
完整的一键部署脚本。

**功能**:
- 依赖检查
- 环境变量准备
- 镜像构建
- 服务启动
- 健康检查

**用法**:
```bash
./scripts/deploy.sh
./scripts/deploy.sh logs  # 查看日志
```

### 2. scripts/start-prod.sh
快速启动脚本。

**用法**:
```bash
./scripts/start-prod.sh
```

### 3. scripts/stop-prod.sh
停止服务脚本。

**用法**:
```bash
./scripts/stop-prod.sh
```

## 配置文件

### gateway/.env
Gateway 环境变量配置。

**关键配置**:
```env
DOUYIN_SERVICE_URL=http://douying-collect:8093
LOG_LEVEL=INFO
PORT=8080
```

## 文档

### 1. DOCKER_DEPLOY.md
快速部署指南。

**内容**:
- 快速开始步骤
- 常用命令
- 服务访问地址
- 故障排查

### 2. docs/deployment.md
完整部署文档。

**内容**:
- 前置要求
- 详细部署步骤
- 服务说明
- 性能优化
- 安全建议
- 监控和日志

## 使用流程

### 首次部署

```bash
# 1. 配置环境变量
cp gateway/.env.example gateway/.env
vim gateway/.env

# 2. 执行部署
./scripts/deploy.sh

# 3. 验证服务
docker ps
curl http://localhost:8080/api/health
```

### 日常维护

```bash
# 启动服务
./scripts/start-prod.sh

# 停止服务
./scripts/stop-prod.sh

# 查看日志
docker compose -f docker-compose.prod.yml logs -f

# 重启服务
docker compose -f docker-compose.prod.yml restart
```

### 更新部署

```bash
# 拉取代码
git pull

# 重新构建
docker compose -f docker-compose.prod.yml build --no-cache

# 重启服务
docker compose -f docker-compose.prod.yml up -d
```

## 文件结构

```
personal-web/
├── docker-compose.prod.yml          # 生产环境配置
├── DOCKER_DEPLOY.md                 # 快速部署指南
├── DEPLOYMENT_FILES.md              # 本文件
├── nginx/
│   └── nginx.conf                   # Nginx 配置
├── scripts/
│   ├── deploy.sh                    # 部署脚本
│   ├── start-prod.sh                # 启动脚本
│   └── stop-prod.sh                 # 停止脚本
├── gateway/
│   ├── Dockerfile                   # Gateway 镜像
│   ├── .dockerignore                # 构建排除
│   └── .env                         # 环境变量
├── frontend/
│   ├── Dockerfile                   # Frontend 镜像
│   └── .dockerignore                # 构建排除
└── docs/
    └── deployment.md                # 完整部署文档
```

## 注意事项

1. **环境变量**: 首次部署前必须配置 `gateway/.env`
2. **端口映射**: 确保服务器防火墙开放相应端口
3. **资源限制**: 根据服务器配置调整容器资源限制
4. **数据备份**: 定期备份 Docker Volumes
5. **日志管理**: 定期清理日志文件，避免磁盘占满

## 相关文档

- [快速部署指南](../DOCKER_DEPLOY.md)
- [完整部署文档](deployment.md)
- [项目 README](../README.md)

---

最后更新: 2025-02
