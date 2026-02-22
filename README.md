# 个人资讯网站

一个部署在阿里云 ECS 上的个人资讯网站，采用微服务架构 + API Gateway + 统一前端的模块化设计。

## 项目结构

```
personal-web/
├── frontend/          # Next.js 统一前端（端口 3000）
├── gateway/           # API Gateway（端口 8080）
├── docs/              # 项目文档
├── discuss/           # 讨论文档
├── scripts/           # 运维脚本
└── docker-compose.yml # Docker Compose 配置
```

## 技术栈

### Gateway
- FastAPI
- HTTPX（异步 HTTP 客户端）
- Python 3.11

### 前端
- Next.js 15.4
- React 19
- Tailwind CSS v4
- TypeScript
- Recharts

## 功能模块

1. **新闻联播分析** - 政策推荐指数、板块影响分析
2. **宏观经济数据** - 汇率、美债收益率、GDP数据
3. **抖音视频文字稿** - 视频列表、文字稿查看、搜索功能

## 独立服务

项目依赖以下独立 GitHub 项目提供后端 API：

- [FinancialDashboard](https://github.com/user/FinancialDashboard) - 宏观经济数据服务（端口 8091）
- [xwlb-analyze](https://github.com/user/xwlb-analyze) - 新闻联播分析服务（端口 8092）
- [douying-collect](https://github.com/user/douying-collect) - 抖音视频转文字稿服务（端口 8093）

## 开发指南

### Gateway 开发

```bash
cd gateway

# 安装依赖
pip install -r requirements.txt

# 运行开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# 访问 API 文档
# http://localhost:8080/docs
```

### 前端开发

```bash
cd frontend

# 安装依赖
pnpm install

# 运行开发服务器
pnpm dev

# 访问网站
# http://localhost:3000
```

### Docker 开发

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 配置

### Gateway 配置

编辑 `gateway/.env`：

```bash
FINANCIAL_SERVICE_URL=http://financial-dashboard:8091
NEWS_SERVICE_URL=http://xwlb-analyze:8092
DOUYIN_SERVICE_URL=http://douying-collect:8093
```

### 前端配置

编辑 `frontend/.env.local`：

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
```

## 部署

### 方式 1: Docker 生产环境（推荐）

使用提供的 Docker Compose 配置一键部署到阿里云 ECS：

```bash
# 快速开始
./scripts/deploy.sh

# 或手动启动
./scripts/start-prod.sh

# 查看日志
docker compose -f docker-compose.prod.yml logs -f

# 停止服务
./scripts/stop-prod.sh
```

**文档**：
- [快速部署指南](DOCKER_DEPLOY.md)
- [完整部署文档](docs/deployment.md)
- [部署文件说明](docs/DEPLOYMENT_FILES.md)

### 方式 2: 本地开发

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 传统部署到阿里云 ECS

1. 克隆三个独立项目并构建 Docker 镜像
2. 克隆 personal-web 项目
3. 配置 `docker-compose.yml`
4. 运行 `docker-compose up -d`

## 架构优势

- ✅ **微服务架构** - 每个模块独立维护和部署
- ✅ **API Gateway** - 统一入口，路由转发
- ✅ **类型安全** - TypeScript + Pydantic 全栈类型
- ✅ **容器化部署** - Docker Compose 一键启动

## License

MIT
