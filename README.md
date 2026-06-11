# 个人财富网站

一个部署在 NAS 上的个人财富管理平台，包含 5 个独立前端应用和 3 个后端服务，全部通过 Docker 运行，由外部 Nginx 统一路由。

## 项目结构

```
personal-web/
├── apps/                    # 5 个独立 Next.js 前端（各有 package.json + Dockerfile）
│   ├── dividend/            # A 股高股息分析（端口 3003，basePath /dividend）
│   ├── douyin/             # 抖音视频文字转写（端口 3004，basePath /douyin）
│   ├── economic/           # 宏观经济（端口 3001）
│   ├── fund-flow/          # 资金流向（端口 3002）
│   └── news/               # 新闻联播分析（端口 3005）
├── backend/                 # 3 个 Python 后端（git submodule）
│   ├── dividend-select/    # 股息率后端（FastAPI，端口 8092）
│   ├── douyin-processor/    # 抖音后端（端口 8093）
│   └── global-macro-fin/   # 宏观金融后端（端口 8094）
├── nginx/                   # 示例 Nginx 配置（参考用）
├── docs/                    # 模块级技术文档
└── docker-compose.yml       # 本地开发用 Docker Compose
```

## 技术栈

### 前端
- Next.js 15.4
- React 19
- TypeScript
- Tailwind CSS v4

### 后端
- Python 3.12
- FastAPI / uvicorn
- akshare、efinance 等数据源

## 功能模块

1. **股息率分析** — A 股高股息选股，支持 TOP10 排名、多股对比、导出报告
2. **宏观经济** — 汇率、美联储利率、GDP 等全球宏观指标
3. **资金流向** — 盘口资金流向可视化
4. **抖音视频转写** — 视频文案自动转写
5. **新闻联播分析** — 政策推荐指数、板块影响分析

## 服务端口一览

| 服务 | 端口 | 说明 |
|------|------|------|
| dividend 前端 | 3003 | basePath /dividend |
| douyin 前端 | 3004 | basePath /douyin |
| economic 前端 | 3001 | |
| fund-flow 前端 | 3002 | |
| news 前端 | 3005 | |
| dividend-select 后端 | 8092 | |
| douyin-processor 后端 | 8093 | |
| global-macro-fin 后端 | 8094 | |

## 快速启动

### 前端开发（以 dividend 为例）
```bash
cd apps/dividend
pnpm dev          # 端口 3003
pnpm build        # 生产构建
```

### 后端开发（以 dividend-select 为例）
```bash
cd backend/dividend-select
uvicorn src.main:app --reload --host 0.0.0.0 --port 8092
```

### Docker 启动（本地）
```bash
docker compose up -d --build
docker compose logs -f
docker compose down
```

### Windows 开发脚本
```bash
scripts\start-dividend-dev.bat   # 股息率前后端
scripts\start-fundflow-dev.bat  # 资金流向
scripts\start-news-dev.bat      # 新闻
scripts\start-macro-dev.bat    # 宏观经济
scripts\start-douyin-dev.bat    # 抖音
```

## NAS 部署

使用 `docker-compose.nas.yml` 在 NAS 上部署：

```bash
# 1. 准备环境变量（在仓库目录创建 .env，填入阿里云 key）
cat > .env << 'EOF'
DIVIDEND_ALIYUN_ACCESS_KEY=你的key
DOUYIN_ALIYUN_ACCESS_KEY=你的key
EOF

# 2. 克隆仓库（包含 submodule）
git clone --recurse-submodules <your-repo-url>

# 3. 启动
docker compose -f docker-compose.nas.yml up -d --build

# 4. 验证
docker compose -f docker-compose.nas.yml ps
```

**网络路由**（由 NAS 上的外部 Nginx 统一对外）：
- `/dividend/*` → dividend-frontend:3003
- `/api/dividend/*` → dividend-backend:8092
- `/douyin/*` → douyin-frontend:3004
- `/api/douyin/*` → douyin-backend:8093

**数据卷**：
- `dividend-data`、`dividend-logs`、`dividend-config`
- `douyin-data`、`douyin-logs`

## 子模块更新流程

三个后端均为 git submodule（`ohyes768/` 账号下独立仓库）：

1. `cd backend/<submodule>` 在子模块内改代码
2. 子模块内 `git add` + `git commit` + `git push origin main`
3. 回到主仓库 `git add backend/<submodule>` 更新 gitlink
4. 主仓库 `git commit -m "chore: bump <submodule> pointer"`
5. 主仓库 `git push origin master`

**顺序很重要**：子模块必须先 push 到远端，主仓库才能 push gitlink 更新。

## 相关文档

- [DOCKER_DEPLOY.md](./DOCKER_DEPLOY.md) — Docker 快速部署指南
- [DEPLOYMENT_FILES.md](./DEPLOYMENT_FILES.md) — 部署文件清单
- [docs/deployment.md](./docs/deployment.md) — 详细部署文档
- [docs/dividend/](docs/dividend/) — 股息率模块技术文档
- [CLAUDE.md](./CLAUDE.md) — 开发者指南

## License

MIT
