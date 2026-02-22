# 阿里云 ECS 部署文档

本文档介绍如何使用 Docker Compose 将 personal-web 项目部署到阿里云 ECS。

## 前置要求

### 1. 服务器要求

- **操作系统**: Ubuntu 20.04+ / CentOS 7+ / Debian 10+
- **CPU**: 2核及以上
- **内存**: 4GB 及以上
- **磁盘**: 20GB 及以上
- **网络**: 公网 IP，开放以下端口：
  - `80` (HTTP)
  - `443` (HTTPS, 如需配置 SSL)
  - `3000` (Frontend, 可选，用于调试)
  - `8080` (Gateway API, 可选，用于调试)
  - `8093` (Douying-Collect, 可选，用于调试)

### 2. 软件要求

服务器需要安装以下软件：

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker --version
docker-compose --version
```

## 部署步骤

### 1. 准备代码

将项目代码上传到服务器，推荐使用 Git：

```bash
# 克隆项目（假设你有自己的 Git 仓库）
git clone <your-repo-url> /opt/personal-web
cd /opt/personal-web

# 或者使用 scp 上传代码
# scp -r ./personal-web root@your-ecs-ip:/opt/
```

### 2. 配置环境变量

编辑 `gateway/.env` 文件，配置必要的环境变量：

```bash
cd /opt/personal-web

# 如果不存在 .env，从示例复制
cp gateway/.env.example gateway/.env

# 编辑配置
vim gateway/.env
```

需要配置的关键变量：

```env
# Gateway 配置
DOUYIN_SERVICE_URL=http://douying-collect:8093

# 其他服务配置...
# 根据你的实际需求配置
```

### 3. 构建和启动

使用提供的部署脚本：

```bash
# 方式1: 使用完整部署脚本
./scripts/deploy.sh

# 方式2: 手动启动
./scripts/start-prod.sh
```

### 4. 检查服务状态

```bash
# 查看运行中的容器
docker ps

# 查看服务日志
docker compose -f docker-compose.prod.yml logs -f

# 检查健康状态
curl http://localhost:8080/api/health
curl http://localhost:3000
curl http://localhost:8093/api/health
```

## 服务说明

### 架构图

```
                    Nginx (80)
                     /    |    \
                    /     |     \
                   /      |      \
        Frontend    Gateway   Douying-Collect
          :3000      :8080        :8093
```

### 服务列表

| 服务名 | 端口 | 说明 |
|--------|------|------|
| frontend | 3000 | Next.js 前端应用 |
| gateway | 8080 | FastAPI 网关服务 |
| douying-collect | 8093 | 抖音数据采集服务 |
| nginx | 80 | 反向代理（可选） |

### 数据持久化

以下数据通过 Docker Volumes 持久化：

- `douying-data`: 采集的视频数据
- `douying-cache`: 处理缓存
- `douying-logs`: 应用日志

## 常用命令

### 服务管理

```bash
# 启动服务
./scripts/start-prod.sh

# 停止服务
./scripts/stop-prod.sh

# 重启服务
docker compose -f docker-compose.prod.yml restart

# 查看日志
docker compose -f docker-compose.prod.yml logs -f [service-name]

# 进入容器
docker exec -it <container-name> bash
```

### 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建镜像
docker compose -f docker-compose.prod.yml build --no-cache

# 重启服务
docker compose -f docker-compose.prod.yml up -d
```

### 清理数据

```bash
# 停止并删除容器
docker compose -f docker-compose.prod.yml down

# 删除数据卷（谨慎操作）
docker volume rm personal-web_douying-data
docker volume rm personal-web_douying-cache
docker volume rm personal-web_douying-logs
```

## 故障排查

### 1. 服务无法启动

```bash
# 查看详细日志
docker compose -f docker-compose.prod.yml logs

# 检查配置文件
cat docker-compose.prod.yml
```

### 2. 端口冲突

如果端口被占用，修改 `docker-compose.prod.yml` 中的端口映射：

```yaml
ports:
  - "新端口:容器端口"
```

### 3. 权限问题

```bash
# 确保脚本有执行权限
chmod +x scripts/*.sh

# 确保数据目录权限正确
mkdir -p data
chmod 755 data
```

### 4. 内存不足

```bash
# 查看资源使用情况
docker stats

# 限制容器资源（在 docker-compose.prod.yml 中配置）
services:
  frontend:
    deploy:
      resources:
        limits:
          memory: 512M
```

## 性能优化

### 1. 启用 Nginx 缓存

编辑 `nginx/nginx.conf`，根据需要调整缓存配置。

### 2. 配置 CDN

将静态资源上传到阿里云 OSS，并配置 CDN 加速。

### 3. 数据库优化

如果数据量较大，考虑使用独立的数据库服务（如 MySQL、MongoDB）。

## 安全建议

1. **防火墙配置**: 只开放必要的端口
2. **HTTPS 配置**: 使用 Let's Encrypt 免费证书
3. **定期备份**: 定期备份数据卷
4. **更新维护**: 定期更新 Docker 镜像和系统补丁

## 监控和日志

### 查看日志

```bash
# 所有服务日志
docker compose -f docker-compose.prod.yml logs

# 特定服务日志
docker compose -f docker-compose.prod.yml logs gateway
docker compose -f docker-compose.prod.yml logs frontend
docker compose -f docker-compose.prod.yml logs douying-collect
```

### 日志文件位置

- Gateway: 容器内 `/app/logs`
- Douying-Collect: 容器内 `/app/logs`，挂载到卷 `douying-logs`

## 联系支持

如遇到问题，请查看：
- 项目 GitHub Issues
- 技术文档: `docs/`
- 配置示例: `*.example` 文件

---

最后更新: 2025-02
