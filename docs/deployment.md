# 个人财富网站部署指南

本文档介绍如何在 NAS 上部署 personal-web 项目。

## 前置要求

### 1. 服务器要求
- **操作系统**: Ubuntu 20.04+ / Debian 10+
- **Docker**: 已安装 Docker 和 Docker Compose
- **网络**: NAS 上已有外部 Nginx，端口 80/443 对外

### 2. 开放端口
- `80` (HTTP，由外部 Nginx 监听)
- `443` (HTTPS，可选)
- NAS 内部通信由 Docker 网络处理，无需额外开放

### 3. 已有的 Nginx 反向代理
NAS 上需要配置好 Nginx，将以下路径转发到对应容器：
- `/dividend/*` → dividend-frontend:3003
- `/api/dividend/*` → dividend-backend:8092
- `/douyin/*` → douyin-frontend:3004
- `/api/douyin/*` → douyin-backend:8093

## 部署步骤

### 1. 准备代码

```bash
# 克隆仓库（包含 submodule）
git clone --recurse-submodules <your-repo-url> /opt/personal-web
cd /opt/personal-web

# 如果已经 clone 但还没有 submodule
git submodule update --init --recursive
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```bash
cd /opt/personal-web
cat > .env << 'EOF'
DIVIDEND_ALIYUN_ACCESS_KEY=你的阿里云key
DOUYIN_ALIYUN_ACCESS_KEY=你的阿里云key
EOF
```

### 3. 启动服务

```bash
# 构建并启动所有服务
docker compose -f docker-compose.nas.yml up -d --build

# 查看服务状态
docker compose -f docker-compose.nas.yml ps
```

### 4. 验证

```bash
# 检查 dividend 后端健康
curl http://localhost:8092/api/dividend/health

# 检查 dividend 前端
curl http://localhost:3003/dividend

# 查看日志
docker compose -f docker-compose.nas.yml logs -f
```

## 服务说明

### 架构图
```
外部 Nginx (:80)
  ├── /dividend/*     → dividend-frontend:3003
  ├── /api/dividend/* → dividend-backend:8092
  ├── /douyin/*       → douyin-frontend:3004
  └── /api/douyin/*   → douyin-backend:8093
```

### 服务列表

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| dividend 后端 | dividend-backend | 8092 | 股息率 FastAPI |
| dividend 前端 | dividend-frontend | 3003 | Next.js standalone |
| douyin 后端 | douyin-backend | 8093 | 抖音处理服务 |
| douyin 前端 | douyin-frontend | 3004 | Next.js standalone |

### 数据卷

| 卷名 | 用途 |
|------|------|
| dividend-data | 股息率 CSV 数据 |
| dividend-logs | 股息率服务日志 |
| dividend-config | 股息率配置 |
| douyin-data | 抖音视频数据 |
| douyin-logs | 抖音服务日志 |

## 常用维护命令

### 启动/停止
```bash
docker compose -f docker-compose.nas.yml up -d
docker compose -f docker-compose.nas.yml down
```

### 重启
```bash
docker compose -f docker-compose.nas.yml restart
```

### 更新部署
```bash
# 拉取最新代码
git pull

# 更新 submodule
git submodule update --init --recursive

# 重新构建镜像
docker compose -f docker-compose.nas.yml build --no-cache

# 重启服务
docker compose -f docker-compose.nas.yml up -d
```

### 查看日志
```bash
# 所有服务日志
docker compose -f docker-compose.nas.yml logs -f

# 特定服务
docker compose -f docker-compose.nas.yml logs -f dividend-backend
docker compose -f docker-compose.nas.yml logs -f dividend-frontend
```

### 进入容器调试
```bash
docker exec -it dividend-backend bash
docker exec -it dividend-frontend sh
```

## 数据备份

```bash
# 备份股息率数据
docker run --rm -v dividend-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/dividend-data-backup.tar.gz /data

# 备份抖音数据
docker run --rm -v douyin-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/douyin-data-backup.tar.gz /data
```

## 故障排查

### 1. 服务无法启动
```bash
docker compose -f docker-compose.nas.yml logs [service-name]
```

### 2. 健康检查失败
```bash
# 手动检查后端
curl http://dividend-backend:8092/api/dividend/health

# 检查容器网络
docker network ls | grep nginx
docker inspect dividend-backend | grep -A5 Networks
```

### 3. 端口冲突
修改 `docker-compose.nas.yml` 中的端口映射：
```yaml
ports:
  - "新端口:容器端口"
```

## 相关文档

- [DOCKER_DEPLOY.md](../DOCKER_DEPLOY.md) — Docker 快速部署指南
- [DEPLOYMENT_FILES.md](../DEPLOYMENT_FILES.md) — 部署文件清单
- [README.md](../README.md) — 项目总览
- [docs/dividend/](docs/dividend/) — 股息率模块技术文档

---

最后更新: 2026-06
