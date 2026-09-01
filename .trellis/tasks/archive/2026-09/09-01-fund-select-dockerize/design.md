# fund-select Docker 化 — 技术设计

> PRD 见 `prd.md`。本文锁定技术决策与权衡。

## 1. 边界

| 落在哪里 | 文件 | 不落在哪里 |
|---|---|---|
| `F:/personal-projects/fund-select/backend/Dockerfile` | backend 镜像构建 | — |
| `F:/personal-projects/fund-select/backend/.dockerignore` | 缩小 build context | — |
| `F:/personal-projects/fund-select/frontend/Dockerfile` | frontend 镜像构建 | — |
| `F:/personal-projects/fund-select/frontend/.dockerignore` | 缩小 build context | — |
| `F:/personal-projects/fund-select/docker-compose.yml` | 本仓独立编排 | — |
| `F:/personal-projects/fund-select/.env.example` | 环境变量样例 | — |
| `F:/personal-projects/fund-select/README.md` | 追加「Docker 部署」小节 | — |
| `F:/personal-projects/personal-web/nginx/web.conf` | 新增 fund-select upstream + location，根路径聚合页加链接 | 不动已有 4 个服务的路由 / SSL |
| `F:/personal-projects/personal-web/docker-compose.nas.yml` | 新增 fund-select-backend / fund-select-frontend + 4 volume；头部注释更新 | 不动已有 4 个 service / 网络定义 |
| `F:/personal-projects/personal-web/CLAUDE.md` | 补 fund-select 后端 / 前端开发命令 | 不动架构说明段（fund-select 独立） |

理由：fund-select 与 personal-web 是两个独立仓库、两个独立部署单元。强行在 personal-web 的 compose 里引用 fund-select 的相对路径会引入跨仓耦合，且 `docker compose -f` 跨目录 `build.context` 在 buildx 上有兼容性坑。

## 2. 后端镜像设计

**基镜像**：`python:3.12-slim`（与 `backend/dividend-select/Dockerfile` 一致；fastapi / akshare / pandas 在 slim 上跑得动，不需要 alpine glibc 兼容）

**镜像源**：apt 阿里云 + pip 清华。原因：
- NAS 在国内；docker hub 拉镜像可能慢，但 image 层（`python:3.12-slim`）已经缓存到本地则无所谓
- akshare 依赖链长（pandas + numpy + lxml + openpyxl），清华源稳定

**时区**：`tzdata` 包 + `ENV TZ=Asia/Shanghai`。slim 镜像不带 zoneinfo，scheduler 的 `datetime.now()`、SQLite 文件 mtime、log 时间戳都会停在 UTC；不修就是隐蔽 bug。

**依赖安装**：`uv sync --frozen --no-dev`
- 用 `uv.lock` 而非 pip：保证 lock 一致；CI 上能严格复现
- `--no-dev`：pytest 不进镜像

**目录约定**（与 src 实际路径对齐）：
```
/app
├── pyproject.toml
├── uv.lock
├── config/        # COPY 进去，挂卷后会被 volume 覆盖
├── src/
└── data/ logs/ cache/   # 容器内创建，由 volume 接管
```

**端口**：从 `SERVER_PORT` 环境变量读（`src/utils/config.py:23` 已实现）。Dockerfile 不硬编码 8095，让 compose 可调。

**Healthcheck**：`curl -f http://localhost:${SERVER_PORT:-8095}/api/funds/health`
- 路由在 `src/api/routes.py:30`（`@router.get("/health")`）
- `main.py:70` 注册到 prefix=`/api/funds`
- 路径必须带 `/api/funds` 前缀，命中 host 上 200 才算 healthy

**启动命令**：
```sh
sh -c "uvicorn src.main:app --host 0.0.0.0 --port ${SERVER_PORT:-8095}"
```
- 直接 uvicorn，不上 gunicorn。**已知 uvicorn 在某些 Linux libc 版本下会 SIGSEGV**（参考 `uvicorn-sigsegv-fix` skill）；本次先打通用、留 follow-up
- 走 venv 的 uvicorn：上一步 `uv sync` 已把 uvicorn 装在 `/app/.venv/`，且 `ENV PATH="/app/.venv/bin:$PATH"`

## 3. 前端镜像设计

**多阶段**（照搬 `apps/dividend/Dockerfile`）：
1. `deps`：装 pnpm + `pnpm install --frozen-lockfile`，cache mount `/root/.local/share/pnpm/store`
2. `builder`：`pnpm build` → 产出 `.next/standalone` + `.next/static`
3. `runner`：仅拷贝 standalone + static + public，非 root 用户（`nextjs` uid=1001）

**为什么不用 `output: 'export'`**：fund-select 用了 API 路由代理（`app/api/funds/[...path]/route.ts`，BFF catch-all 转发到 backend），必须 standalone 跑 Node server。

**basePath**：`/funds`（`next.config.js:4`）。容器内 `next start -p 3005` 后，访问 `/funds` 才命中首页。NAS nginx 转 `http://fund-select-frontend:3005/funds` 必须保留 `/funds` 前缀。

**为什么不用 BFF 直连**：当前 v1 已有 `app/api/funds/[...path]/route.ts` 作为 BFF catch-all，转发到 `http://fund-select-backend:8095`。Docker 里通过 `BACKEND_URL=http://fund-select-backend:8095`（compose 注入）让 BFF 找到后端 service name。

**env 注入**：
- `BACKEND_URL=http://fund-select-backend:8095`（runtime env）
- 不需要 build-time `NEXT_PUBLIC_*`（v1 没用到）

## 4. Compose 设计

**2 个 service + 1 个 network + 4 个 volume**：

```yaml
services:
  fund-select-backend:    # 健康检查通过后才起 frontend
  fund-select-frontend:   # depends_on backend healthy

networks:
  app-net:                # 独立 bridge；用户可手动接到 NAS 的 nginx_nginx-bridge

volumes:
  fund-select-data:       # /app/data，SQLite funds.db
  fund-select-cache:      # /app/cache，akshare / 费率 / 经理表 JSON
  fund-select-config:     # /app/config/funds.yaml（31 只名单）
  fund-select-logs:       # /app/logs
```

**端口映射**：
- backend：`expose: ["8095"]`（不暴露宿主机端口，只在 network 内可达；前端通过 service name 访问）
- frontend：`ports: ["127.0.0.1:3005:3005"]`（绑本地回环；NAS 上由外部 nginx 反代，参考 personal-web 模式）

**为什么不 bind mount**：named volume 更接近 NAS 部署形态（数据在 `/var/lib/docker/volumes/`），bind mount 容易踩 Windows / WSL 路径转换坑。**例外**：`fund-select-config` 如果用户希望直接编辑 `funds.yaml` 触发 reload，可以改成 `./config:/app/config`；本次先用 named volume，等需求来了再切。

**重启策略**：`restart: unless-stopped`（对齐 personal-web 所有服务）

**healthcheck / depends_on**：让 frontend 等 backend 就绪后再起，避免启动期 502。

## 5. 镜像源与构建加速

**NAS 部署**通常已经在国内，apt/pip 国内源是 must；前端 pnpm 走 npm 官方源（cnpm 镜像同步延迟，反而更慢）。

**BuildKit cache mount**：照搬 dividend Dockerfile 的 `RUN --mount=type=cache,id=pnpm-shared,target=/root/.local/share/pnpm/store`。热构建复用 store，二次构建快 5-10 倍。

## 6. 部署拓扑

```
┌─────────────────────────────────────────────────┐
│ NAS（外部 nginx，假设已存在）                     │
│  /funds/*      → fund-select-frontend:3005      │
│  /api/funds/*  → fund-select-backend:8095       │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ docker-compose.yml (fund-select)                │
│                                                  │
│  fund-select-frontend (3005)                    │
│        │                                         │
│        │ BACKEND_URL=http://fund-select-backend │
│        ▼                                         │
│  fund-select-backend (8095, no host port)       │
│        │                                         │
│        ▼                                         │
│  fund-select-data ─ SQLite                      │
│  fund-select-cache ─ akshare JSON               │
│  fund-select-config ─ funds.yaml                │
│  fund-select-logs ─ 日志                         │
└─────────────────────────────────────────────────┘
```

## 7. 决策记录（已锁）

| 决策 | 选择 | 否决方案 | 理由 |
|---|---|---|---|
| 基镜像（后端） | `python:3.12-slim` | `python:3.12-alpine` | glibc 兼容；akshare 依赖链已验证 |
| 包管理器（后端） | `uv` | `pip` | 有 `uv.lock`，可复现 |
| Web 入口（后端） | `uvicorn` 直接跑 | `gunicorn -k uvicorn.workers.UvicornWorker` | 先打通用，SIGSEGV 留 follow-up |
| 基镜像（前端） | `node:20-alpine` 多阶段 | `node:20-slim` | dividend 已验证；standalone 模式 |
| 构建产物（前端） | Next.js standalone | `output: 'export'` | BFF catch-all 需要 Node server |
| 端口映射（前端） | `127.0.0.1:3005:3005` | `3005:3005` | NAS 由外部 nginx 反代，不直接对外 |
| 端口映射（后端） | `expose` | `8095:8095` | 后端只给前端用，不暴露宿主机 |
| 数据卷 | named volume | bind mount | NAS 部署形态；避 Windows 路径坑 |
| 网络 | 独立 `app-net` | 接 NAS `nginx_nginx-bridge` | 让 fund-select 单独能跑，合并由用户在 NAS 上手做 |
| .env 文件 | 仅 `.env.example`，`.env` 进 `.gitignore` | 提交默认 `.env` | 不泄漏 |
| nginx 配置 | 直接改 `personal-web/nginx/web.conf` | 仅 README 给片段 | 用户要求同仓统一部署 |
| 个人仓 compose 合并 | 在 `docker-compose.nas.yml` 加 2 service（context 指 `../fund-select/...`） | 仅 `fund-select/docker-compose.yml` | 用户要求同仓部署 |

## 8. 跨仓 wiring 设计

**为什么 fund-select backend 内部 8095 端口不与 rss-relay-backend 冲突**：
- `expose: ["8095"]` 是 docker 网络元数据，**不**绑宿主机端口
- 同一 bridge 网络里两个容器都听 8095 没冲突——每个容器有独立 IP，service name 寻址
- nginx upstream 用 `fund-select-backend:8095` 与 `rss-relay-backend:8095` 区分，互不影响

**NAS nginx 上 fund-select 路由参考点**：
- `/funds/_next/static/` → 仿 `/rss/_next/static/`（basePath 同理）
- `/funds` 页面 → 仿 `/rss`（不带尾 /）
- `/api/funds/` → 仿 `/api/macro/`（rewrite 剥 `/api/funds` 前缀 → `/api/<x>`，对齐后端 router prefix）

**`docker-compose.nas.yml` 中 fund-select service 的 `build.context`**：
- 用 `../fund-select/backend` / `../fund-select/frontend`
- 相对路径以 personal-web 仓根为基准；个人项目两仓平级（都在 `F:/personal-projects/`），路径稳定
- 与 `./backend/dividend-select` / `./apps/dividend` 风格一致——只是多一层 `..`

**为什么 fund-select 自带 `docker-compose.yml` 还有意义**：
- 单仓跑得起来（开发态 Windows / 单机 Linux）
- 与 personal-web 的 NAS 编排解耦——用户不接 NAS 时也能用
- 内部卷、healthcheck、网络配置都是同一套；只在 `docker-compose.nas.yml` 多一份镜像构建 + 接外部网络即可
