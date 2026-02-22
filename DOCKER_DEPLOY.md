# Docker 快速部署指南

快速开始使用 Docker 部署 personal-web 项目。

## 快速开始

### 1. 安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun

# 启动 Docker
sudo systemctl start docker
sudo systemctl enable docker
```

### 2. 配置环境

```bash
# 进入项目目录
cd personal-web

# 复制环境变量配置
cp gateway/.env.example gateway/.env

# 编辑配置（根据需要修改）
vim gateway/.env
```

### 3. 一键部署

```bash
# 方式1: 使用部署脚本（推荐）
./scripts/deploy.sh

# 方式2: 手动启动
docker compose -f docker-compose.prod.yml up -d --build
```

### 4. 验证部署

```bash
# 检查服务状态
docker ps

# 访问服务
curl http://localhost:8080/api/health  # Gateway
curl http://localhost:3000             # Frontend
```

## 服务访问

部署完成后，可通过以下地址访问：

- **前端应用**: http://your-server-ip:3000
- **API 网关**: http://your-server-ip:8080
- **API 文档**: http://your-server-ip:8080/docs

## 常用命令

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

## 数据持久化

数据存储在 Docker Volumes 中：

```bash
# 查看数据卷
docker volume ls | grep personal-web

# 备份数据卷
docker run --rm -v personal-web_douying-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/douying-data-backup.tar.gz /data
```

## 详细文档

完整的部署文档请参考: [docs/deployment.md](docs/deployment.md)

## 故障排查

```bash
# 查看容器日志
docker compose -f docker-compose.prod.yml logs [service-name]

# 进入容器调试
docker exec -it <container-name> bash

# 重新构建镜像
docker compose -f docker-compose.prod.yml build --no-cache
```

## 项目结构

```
personal-web/
├── docker-compose.prod.yml    # 生产环境 Docker Compose 配置
├── scripts/
│   ├── deploy.sh              # 一键部署脚本
│   ├── start-prod.sh          # 启动脚本
│   └── stop-prod.sh           # 停止脚本
├── nginx/
│   └── nginx.conf             # Nginx 反向代理配置
├── gateway/
│   ├── Dockerfile             # Gateway 服务镜像
│   └── .env                   # 环境变量配置
├── frontend/
│   └── Dockerfile             # Frontend 服务镜像
└── docs/
    └── deployment.md          # 详细部署文档
```

## 支持

如有问题，请查看 [docs/deployment.md](docs/deployment.md) 获取详细文档。
