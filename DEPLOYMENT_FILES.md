# Docker 部署文件清单

本文档列出了所有用于 NAS 部署的 Docker 相关文件。

## 核心配置文件

### 1. docker-compose.nas.yml
NAS 生产环境 Docker Compose 配置文件。
**位置**: `/docker-compose.nas.yml`

**服务定义**:
- `dividend-backend`: 股息率后端（FastAPI，端口 8092）
- `dividend-frontend`: 股息率前端（Next.js standalone，端口 3003）
- `douyin-backend`: 抖音后端（端口 8093）
- `douyin-frontend`: 抖音前端（Next.js standalone，端口 3004）

**数据卷**: dividend-data, dividend-logs, dividend-config, douyin-data, douyin-logs

**网络**: 连接外部 Nginx 网桥 `nginx_nginx-bridge`

### 2. docker-compose.yml
本地开发用 Docker Compose 配置文件。
**位置**: `/docker-compose.yml`

**服务定义**: macro, dividend, douyin, news 四个前端

### 3. nginx/web.conf
NAS 上 nginx 容器的反向代理配置（source of truth，已纳入版本管理）。
**位置**: `/nginx/web.conf`

**说明**: NAS nginx 是独立容器（容器名 `nginx`），不在 docker-compose.nas.yml 内。
改 web.conf 后部署：`./scripts/deploy-nas.sh nginx`（自动 `docker cp` 进容器 + `nginx -t` + `nginx -s reload`）。
容器名/路径可用环境变量覆盖：`NGINX_CONTAINER` / `NGINX_CONF_DEST`（默认 `/etc/nginx/conf.d/web.conf`）。

## Dockerfiles

### 前端（apps/*/Dockerfile）
每个前端 app 独立 Dockerfile，基于 `node:20-alpine`，三阶段构建：

| App | Dockerfile | 端口 | basePath |
|----|-----------|------|----------|
| dividend | `apps/dividend/Dockerfile` | 3003 | /dividend |
| douyin | `apps/douyin/Dockerfile` | 3004 | /douyin |
| macro | `apps/macro/Dockerfile` | 3001 | /macro |
| news | `apps/news/Dockerfile` | 3005 | 无 |

构建方式: standalone，三阶段（deps → builder → runner）

### 后端（backend/*/Dockerfile）

| 服务 | Dockerfile | 端口 | 说明 |
|------|-----------|------|------|
| dividend-select | `backend/dividend-select/Dockerfile` | 8092 | FastAPI，uvicorn |
| douyin-processor | `backend/douyin-processor/Dockerfile` | 8093 | uvicorn src.server.main |
| macro | `backend/macro/Dockerfile` | 8094 | .venv/bin/uvicorn |

## 环境变量

### dividend-select
`backend/dividend-select/.env.example` → `.env.local`

关键配置:
- `ALIYUN_ACCESS_KEY`: 阿里云行情 API key
- `LOG_LEVEL`: 日志级别（INFO）

### douyin-processor
`backend/douyin-processor/.env.example` → `.env`

关键配置:
- `ALIYUN_ACCESS_KEY`: 阿里云 key

### 全局（项目根目录 .env）
```
DIVIDEND_ALIYUN_ACCESS_KEY=你的key
DOUYIN_ALIYUN_ACCESS_KEY=你的key
```

## 部署流程

```bash
# 1. 准备 .env
cat > .env << 'EOF'
DIVIDEND_ALIYUN_ACCESS_KEY=你的key
DOUYIN_ALIYUN_ACCESS_KEY=你的key
EOF

# 2. 克隆（包含 submodule）
git clone --recurse-submodules <repo-url>

# 3. 启动
docker compose -f docker-compose.nas.yml up -d --build

# 4. 验证
docker compose -f docker-compose.nas.yml ps
```

## 数据卷说明

| 卷名 | 用途 |
|------|------|
| dividend-data | 股息率数据（CSV 等） |
| dividend-logs | 股息率服务日志 |
| dividend-config | 股息率配置文件 |
| douyin-data | 抖音视频数据 |
| douyin-logs | 抖音服务日志 |

## 相关文档

- [DOCKER_DEPLOY.md](../DOCKER_DEPLOY.md) — 快速部署指南
- [docs/deployment.md](../docs/deployment.md) — 详细部署文档
- [README.md](../README.md) — 项目总览

---

最后更新: 2025-06
