# Docker 快速部署指南

快速启动使用 Docker 部署 personal-web 项目。

## 快速启动

### 1. 准备环境变量
```bash
# 在项目目录创建 .env 文件，填入阿里云 key
cat > .env << 'EOF'
DIVIDEND_ALIYUN_ACCESS_KEY=你的key
DOUYIN_ALIYUN_ACCESS_KEY=你的key
EOF
```

### 2. 克隆仓库
```bash
# 包含 submodule
git clone --recurse-submodules <your-repo-url>
cd personal-web

# 如果已经 clone 但没有 submodule
git submodule update --init --recursive
```

### 3. 启动
```bash
# 本地开发
docker compose up -d --build

# NAS 部署
docker compose -f docker-compose.nas.yml up -d --build
```

### 4. 验证
```bash
docker compose ps
curl http://localhost:3003/dividend   # dividend 前端
curl http://localhost:8092/api/dividend/health  # dividend 后端健康检查
```

## NAS 部署说明

`docker-compose.nas.yml` 用于 Ubuntu Server NAS，包含 dividend + douyin 两个完整场景。

**网络路由**（由 NAS 上外部 Nginx 统一对外）：
- `/dividend/*` → dividend-frontend:3003
- `/api/dividend/*` → dividend-backend:8092
- `/douyin/*` → douyin-frontend:3004
- `/api/douyin/*` → douyin-backend:8093

**数据持久化**（使用 named volume）：
- `dividend-data`、`dividend-logs`、`dividend-config`
- `douyin-data`、`douyin-logs`

## 常用命令

```bash
# 启动
docker compose -f docker-compose.nas.yml up -d

# 停止
docker compose -f docker-compose.nas.yml down

# 查看日志
docker compose -f docker-compose.nas.yml logs -f [service-name]

# 重启
docker compose -f docker-compose.nas.yml restart

# 重新构建
docker compose -f docker-compose.nas.yml up -d --build
```

## 数据备份

```bash
# 备份数据卷
docker run --rm -v dividend-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/dividend-data-backup.tar.gz /data
```

## 故障排查

```bash
# 查看容器日志
docker compose -f docker-compose.nas.yml logs [service-name]

# 进入容器调试
docker exec -it <container-name> bash

# 重新构建镜像（跳过缓存）
docker compose -f docker-compose.nas.yml build --no-cache
```

## 详细文档

- [docs/deployment.md](docs/deployment.md) — 详细部署文档
- [DEPLOYMENT_FILES.md](DEPLOYMENT_FILES.md) — 部署文件清单
- [README.md](README.md) — 项目总览
