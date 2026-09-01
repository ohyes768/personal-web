# 基金筛选平台 Docker 化部署

## Goal

为独立项目 `F:/personal-projects/fund-select/`（v1 债基筛选，31 只精选基金）补齐 Docker 部署文件，使其能从 Windows `.bat` 本地启动升级为可重复的容器化部署（NAS / Linux）。

最终产物：3 个 Docker 文件 + 1 个示例 .env + 1 段 NAS nginx 路由配置建议，全部落在 fund-select 仓库内。

## Background

- 项目位置：`F:/personal-projects/fund-select/`（独立 repo，不在 personal-web monorepo）
- 当前部署：`scripts/start-fund-select-*.bat` + `scripts/stop-fund-select-dev.bat`，只支持 Windows 本地
- 后端：`backend/`（FastAPI + akshare + APScheduler + SQLite，端口 8095）
- 前端：`frontend/`（Next.js 15 standalone，端口 3005，basePath=`/funds`）
- 已在 `apps/dividend/` `apps/douyin/` `backend/dividend-select/` 等有可复用的 Dockerfile / compose 模式
- 数据卷关键文件：`config/funds.yaml`（31 只配置）、`data/funds.db`（SQLite）、`cache/`（akshare / 东财费率 / 经理表 JSON 缓存）、`logs/`

## Requirements

### R1：后端 Dockerfile

- `backend/Dockerfile`：基于 `python:3.12-slim`，参照 `backend/dividend-select/Dockerfile` 模式
  - 配置 apt + pip 国内镜像源（阿里云 + 清华）
  - 安装 `tzdata`、`curl`；设置 `TZ=Asia/Shanghai`
  - 用 `uv sync --frozen --no-dev` 从 `uv.lock` 安装
  - 暴露端口从 `SERVER_PORT` 环境变量读，默认 8095
  - Healthcheck 命中 `GET /api/funds/health`（router prefix=`/api/funds`，`@router.get("/health")` 在 `routes.py:30`）
  - CMD 走 uvicorn 即可（暂不上 gunicorn，留作 follow-up；本次先打通端到端）
- `.dockerignore`：排除 `.venv/`、`__pycache__/`、`tests/`、`data/`、`cache/`、`logs/`、`*.pyc`、`.env*`

### R2：前端 Dockerfile

- `frontend/Dockerfile`：参照 `apps/dividend/Dockerfile`
  - 多阶段：`deps`（pnpm install 缓存 mount）→ `builder`（`pnpm build` standalone）→ `runner`（`node server.js`）
  - 必须支持 `output: 'standalone'`（`next.config.js:3` 已配）
  - EXPOSE 3005；PORT/HOSTNAME env 配套
  - 不读 `NEXT_PUBLIC_*` 之外的 build-time env（当前前端没有 BFF，反代由 NAS nginx 直转后端 8095）

### R3：根目录 docker-compose.yml

- 位置：`F:/personal-projects/fund-select/docker-compose.yml`
- 2 个 service：`fund-select-backend`（8095）+ `fund-select-frontend`（3005）
- volume 用 **named volume**（与 personal-web `docker-compose.nas.yml` 保持一致，docker 自动管理）：
  - `fund-select-data` → `/app/data`
  - `fund-select-cache` → `/app/cache`
  - `fund-select-config` → `/app/config`（如 `funds.yaml` 需要宿主机编辑，则改 bind mount）
  - `fund-select-logs` → `/app/logs`
- network：声明独立 `app-net`（bridge），**不强制 external**（让 fund-select 单独能起；用户后续可手动接入 NAS 的 `nginx_nginx-bridge`）
- backend healthcheck → frontend `depends_on: condition: service_healthy`
- 提供 `.env.example` 列出可调环境变量（`SERVER_PORT`、`LOG_LEVEL`、`TZ`，留空即默认值）

### R4：NAS nginx 路由

- 改 `F:/personal-projects/personal-web/nginx/web.conf`：
  - 新增 `upstream fund_select_backend { zone ...; server fund-select-backend:8095 resolve; keepalive 16; }`
  - 新增 `upstream fund_select_frontend { zone ...; server fund-select-frontend:3005 resolve; keepalive 16; }`
  - 静态资源 `location /funds/_next/static/` → `proxy_pass http://fund_select_frontend/funds/_next/static/;`（仿 `/rss/_next/static/`）
  - 页面 `location /funds`（不带尾 /，避免 trailingSlash 跳转循环，仿 `/rss`）→ `proxy_pass http://fund_select_frontend;`
  - API `location /api/funds/` → `rewrite ^/api/funds/(.*)$ /api/$1 break; proxy_pass http://fund_select_backend;`（仿 `/api/macro/`，剥前缀对齐后端 router prefix `/api/funds`）
  - 根路径聚合页 HTML 加一条 `<a href="/funds/">📈 基金筛选</a>`
- 顺序：upstream 定义追加在文件末尾的 upstream 块（line 36 后）；location 块按 macro 模板插在末尾
- 不动已有 4 个服务的路由与 SSL 配置

### R5：personal-web docker-compose.nas.yml 合并

- 改 `F:/personal-projects/personal-web/docker-compose.nas.yml`：
  - 新增 `fund-select-backend` service：`build.context = ../fund-select/backend`，`expose: ["8095"]`，volumes 同 fund-select 自带 compose，env 注入 `TZ=Asia/Shanghai / SERVER_PORT=8095 / LOG_LEVEL=INFO`，healthcheck 命中 `/api/funds/health`，接 `nginx_nginx-bridge`
  - 新增 `fund-select-frontend` service：`build.context = ../fund-select/frontend`，`ports: ["127.0.0.1:3005:3005"]`，env 注入 `BACKEND_URL=http://fund-select-backend:8095`（前端 BFF 用），`depends_on` backend healthy
  - 新增 4 个 named volume：`fund-select-data` / `fund-select-cache` / `fund-select-config` / `fund-select-logs`
  - 文件头部注释块更新「网络路由」段补 `/funds/*` 与 `/api/funds/*` 路由
- 注意：`fund-select-backend` 与 `rss-relay-backend` 都是内部 8095 端口，**不会**冲突——docker bridge 网络里容器有独立 IP，service name 才是寻址关键

### R6：文档

- 在 `F:/personal-projects/fund-select/README.md` 末尾追加「Docker 部署」小节（命令 + 卷说明 + nginx 配置提示）
- 在 `F:/personal-projects/personal-web/CLAUDE.md` 的「常用命令」表格下追加 fund-select 后端 / 前端开发命令（如 `cd ../fund-select/backend && uv sync && ...`），并在「关键 API 路由」段（如果合适）补一笔 fund-select 的 `/api/funds`
- **不** 在 personal-web CLAUDE.md 的「架构说明」加 fund-select 子图（fund-select 是独立项目）

## Out of scope

- 改 fund-select 应用代码本身（这次只动部署文件）
- 上 gunicorn（uvicorn SIGSEGV 风险留作 follow-up；本次先打通用）
- 加 nginx 容器（NAS 已有外部 nginx，按 personal-web 既有模式走外部反代）
- 自动 push 到镜像仓库（NAS 上 buildx 即可）
- 接入 personal-web `docker-compose.nas.yml`（留用户在 NAS 端手动合并）
- ARM64 镜像 cross-build（先 x86_64，NAS 主流是 x86）
- HTTPS / 域名证书（NAS 端统一处理）

## Acceptance Criteria

### 部署文件齐备

- [ ] `F:/personal-projects/fund-select/backend/Dockerfile` 存在；`docker build` 在 Linux / WSL2 / Docker Desktop 上能成功
- [ ] `F:/personal-projects/fund-select/backend/.dockerignore` 存在
- [ ] `F:/personal-projects/fund-select/frontend/Dockerfile` 存在；`docker build` 成功
- [ ] `F:/personal-projects/fund-select/frontend/.dockerignore` 存在
- [ ] `F:/personal-projects/fund-select/docker-compose.yml` 存在，`docker compose config` 校验通过
- [ ] `F:/personal-projects/fund-select/.env.example` 存在

### personal-web 集成

- [ ] `nginx/web.conf` 新增 2 个 upstream 块 + 3 个 location 块（静态 / 页面 / API），无语法错误
- [ ] 根路径聚合页 HTML 加上 `/funds/` 链接
- [ ] `docker-compose.nas.yml` 新增 2 个 service + 4 个 named volume；文件头注释更新网络路由段
- [ ] `docker compose -f docker-compose.nas.yml config` 校验通过

### 容器起得来（fund-select 自带 compose）

- [ ] `docker compose up -d --build` 在 Windows / Linux / NAS 任一环境成功
- [ ] `docker compose ps` 显示 backend + frontend 都是 healthy（依赖 healthcheck 通过）
- [ ] `docker compose logs fund-select-backend` 无致命错误；scheduler 启动日志可见

### 接口可达

- [ ] 宿主机 `curl http://localhost:8095/api/funds/health` 返回 200
- [ ] 宿主机 `curl http://localhost:3005/funds` 返回 200（HTML 首页）
- [ ] 宿主机 `curl http://localhost:8095/api/funds/screen` 返回 31 只 JSON 数组（或 0 只，看空库 vs 引导数据）
- [ ] 容器内 `curl http://fund-select-backend:8095/api/funds/health` 走 service name 通（证明内部网络通）
- [ ] （若在 NAS 跑）`curl https://web.duomi77.cn/funds/` 返回 200（走 nginx + docker-compose.nas.yml）

### 数据卷正确

- [ ] 在宿主机向 `fund-select-data` volume 内放 `results_31.csv` 引导数据 → 重启 backend 后 31 只可查
- [ ] 改 `fund-select-config/funds.yaml` 列表后重启 backend，`GET /api/funds/screen` 数量同步（说明卷挂载生效）
- [ ] backend 重启后 `fund-select-data/funds.db` 仍存在（SQLite 持久化）

### 文档

- [ ] `F:/personal-projects/fund-select/README.md` 末尾新增「Docker 部署」小节
- [ ] `F:/personal-projects/personal-web/CLAUDE.md` 补 fund-select 后端 / 前端开发命令
- [ ] nginx + docker-compose.nas.yml 文件头注释指引清晰

## Risks

| 风险 | 缓解 |
|---|---|
| uvicorn SIGSEGV（已知 issue） | 走 gunicorn 是更好实践，但本次先打通用；follow-up 用 `uvicorn-sigsegv-fix` skill |
| akshare 在容器内被东方财富节流 | 与 Windows 同；scheduler 自带 tenacity 重试（commit `6f70296`） |
| akshare 在容器内找不到 zoneinfo | `tzdata` 包已装 + `TZ=Asia/Shanghai` |
| `uv sync --frozen` 因 lock 与 pyproject 不一致失败 | 部署前本地 `uv lock` 已确保一致；CI 上若失败回退 `uv sync` |
| Next.js standalone 漏拷 `.next/static` / `public` | 模板照搬 dividend Dockerfile，已验过 |
| 镜像体积大 | 不优化（第一版以可跑通为准；alpine slim + 多阶段已能砍大部分） |

## References

- 复用模式：`apps/dividend/Dockerfile`、`backend/dividend-select/Dockerfile`、`backend/dividend-select/docker-compose.yml`、`docker-compose.nas.yml`
- 上游任务：`.trellis/tasks/archive/2026-09/09-01-fund-select-v1-bond/prd.md`
- fund-select README：`F:/personal-projects/fund-select/README.md`
- uvicorn SIGSEGV skill：`uvicorn-sigsegv-fix`（留作 follow-up）
