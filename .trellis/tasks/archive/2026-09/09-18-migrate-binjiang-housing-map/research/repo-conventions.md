# Research: 目标仓库规范（personal-web monorepo）

- **Query**: 滨江购房地图迁移 — 调研项 B（backend/fund-select + apps/fund-select + macro + nginx + compose + 启动脚本规范）
- **Scope**: internal（F:/personal-projects/personal-web）
- **Date**: 2026-09-18

## B1. backend/fund-select 后端规范（新 backend/housing-map 参照）

### Dockerfile（`backend/fund-select/Dockerfile`）

- 基础镜像 `python:3.12-slim`；apt 换阿里云镜像；装 `curl tzdata`；`ENV TZ=Asia/Shanghai`（L12，slim 缺 zoneinfo 会导致时间停在 UTC）。
- pip 配清华源（L15）+ `pip install uv`（L18）。
- COPY 顺序（L23-26）：`pyproject.toml` → `uv.lock` → `config/` → `src/`（**不 COPY data/**，数据走 volume）。
- `RUN uv sync --frozen --no-dev`（L29）；`ENV PATH="/app/.venv/bin:$PATH"`（L32）。
- `RUN mkdir -p data logs cache`（L35）。
- HEALTHCHECK（L41-42）：`curl -f http://localhost:${SERVER_PORT:-8095}/api/funds/health`。
- CMD（L46）：`uvicorn src.main:app --host 0.0.0.0 --port ${SERVER_PORT:-8095}`（端口从 env 读，不硬编码）。

### src/ 目录结构

```
backend/fund-select/src/
├── main.py            # 应用入口
├── api/
│   ├── routes.py      # APIRouter + 端点
│   └── models.py      # Pydantic 模型
├── data/              # 各数据 fetcher（抓取逻辑）
├── db/                # models.py + session.py（SQLite）
├── scheduler/         # APScheduler 定时任务
├── services/          # 业务服务
└── utils/             # config.py / logger.py
```

### main.py 关键写法（`backend/fund-select/src/main.py`）

- L9-16：`load_dotenv(.env)` + `load_dotenv(.env.local, override=True)`，在所有 import 前（.env.local 优先级最高；缺 python-dotenv 不报错）。
- L39-58：`lifespan` 异步上下文——启动时 init_db + 启动调度器，关闭时 shutdown。
- L67-73：CORS `allow_origins=["*"]`。
- L75-78：`app.include_router(router, prefix="/api/funds")`（router 本身无前缀，前缀在 main 挂载处给）。

### health 端点写法（`backend/fund-select/src/api/routes.py` L45-48）

```python
@router.get("/health", tags=["system"])
async def health():
    """健康检查"""
    return {"status": "ok"}
```

### pyproject.toml 关键配置

- `requires-python = ">=3.11"`；依赖含 fastapi/uvicorn[standard]/pydantic/python-dotenv。
- `[project.optional-dependencies] dev = [pytest, pytest-cov]`。
- **`[tool.uv] package = false`**（L28-29）——应用而非库，uvicorn 从项目根直接跑 `src.main:app`。
- `[tool.pytest.ini_options] testpaths=["tests"]`；ruff `select = ["F401","F841","B017","SIM117","RUF059"]`（显式 5 类基线，注释解释不用 extend-select 的原因 L37-43）；coverage source=["src"]。
- `.env.example`（4 行）：`SERVER_PORT=8095` / `SERVER_HOST=0.0.0.0` / `DATABASE_URL=sqlite:///./data/funds.db` / `LOG_LEVEL=INFO`。

## B2. apps/fund-select 前端规范

### Dockerfile（`apps/fund-select/Dockerfile`）

- node:20-alpine 三阶段（deps / builder / runner）；deps 阶段 `pnpm install --frozen-lockfile` + `--mount=type=cache,id=pnpm-${PNPM_CACHE_BUST}` 缓存（L6-8）。
- runner：`COPY .next/standalone ./` + `.next/static` + `public` 三段拷贝（standalone 不含静态资源，L25-27）；`USER nextjs`；`ENV PORT=3005 HOSTNAME=0.0.0.0`；`CMD ["node","server.js"]`。

### next.config.js（`apps/fund-select/next.config.js`）

```js
const nextConfig = { output: 'standalone', basePath: '/funds' };
```

### BFF 现状（迁移决策：housing-map **不做 BFF**）

- fund-select 有 BFF：`apps/fund-select/src/app/api/funds/[...path]/route.ts` catch-all，`BACKEND_URL || http://localhost:8095` 转发（L6,14），二进制透传保 CSV BOM。
- 但生产 NAS 走 **nginx 直转**（web.conf L232-239），BFF 仅本地开发用。compose 注释（docker-compose.nas.yml L30）："fund-select 前端 BFF 仅本地"。
- **macro 模式即"纯前端无 BFF"的先例**（见 B3），housing-map 应仿 macro。

## B3. apps/macro 前端直接调后端 API 的方式（housing-map 的参照模式）

### next.config.js（`apps/macro/next.config.js`）

```js
const nextConfig = {
  output: 'standalone',
  basePath: '/macro',
  async rewrites() {
    return [{
      // 本地 dev: Next 代理 /api/macro/* → localhost:8094/api/*；生产被 nginx 先拦截
      source: '/api/macro/:path*',
      destination: `${process.env.MACRO_API_ORIGIN || 'http://localhost:8094'}/api/:path*`,
      basePath: false,
    }];
  },
};
```

- `basePath: false` 让 rewrite 源不带 basePath（否则源会是 `/macro/api/macro/...`）。
- 后端 macro router 自带 `prefix="/api"`（`backend/macro/src/api/routes.py` L89），nginx 把 `/api/macro/x` 剥成 `/api/x`（web.conf L201-206）——**dev rewrite 与生产 nginx 剥前缀行为对齐**。

### 前端代码调用方式

- 组件直接相对路径 fetch：`fetch('/api/macro/months')`、`fetch(\`/api/macro/daily-snapshot${qs}\`)`（`apps/macro/src/app/modules/economic/components/MacroSignalTab.tsx` L70, L131）。
- 通用客户端 `apps/macro/src/lib/api-client.ts` L21：`baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || ''`；相对路径时 `url = baseUrl + endpoint`（L60-64）。
- compose 中 macro-frontend 环境变量：`NEXT_PUBLIC_API_BASE_URL=/`（docker-compose.nas.yml L249）——即 baseUrl="/"，endpoint 写 `/api/macro/...`。
- **结论**：housing-map 前端直接 `fetch('/api/map/...')`，`NEXT_PUBLIC_API_BASE_URL=/`（或不经 api-client 直接相对路径），nginx `/api/map/*` 直转；本地 dev 用 next.config rewrites 代理到 `localhost:<housing_port>`。

## B4. .gitignore 对 backend data/ 的处理 + compose volume 模式

- 根 `.gitignore` L76-81 显式忽略 fund-select 运行数据：`backend/fund-select/data/`、`cache/`、`logs/`、`.coverage`、`.pytest_cache/`。
- **dividend 与 macro 的 data/ 同样不入库**（`git ls-files backend/dividend-select/data/` 与 `backend/macro/data/` 均为空）。
- compose 数据卷模式（docker-compose.nas.yml L319-341）：全部 named volume（`fund-select-data:/app/data` 等，名字即卷名）。fund-select 后端 L270 注释：**`/app/config` 不挂 volume**（静态配置随镜像 COPY，挂 volume 会被旧内容遮蔽）。
- 初次部署数据初始化先例：`scripts/init-macro-data.sh`——通过调后端 HTTP 接口拉历史数据（`MACRO_SERVICE_URL` 可覆盖）。housing-map 的静态数据（11 个文件）若不入 git，需要类似的初始化路径（或数据随镜像 COPY + volume 首次复制）。
- **注意**：housing-map 与 fund-select 不同点是数据**只读静态快照 + 一个可写 jsonl**；最小方案是 data/ 随镜像 COPY（改数据需 rebuild）或 volume + 手动灌入，实施时需按已定架构决策二选一。

## B5. scripts/start-*-dev.bat 通用结构

最接近的模板：**`scripts/start-macro-dev.bat`**（前后端一个脚本启动，105 行）。结构：

1. `setlocal enabledelayedexpansion` + 端口变量（`MACRO_API_PORT=8094`、`MACRO_WEB_PORT=3001`）。
2. [1/2] 后端：`netstat -aon | find ":%PORT% "` + `taskkill /F /T /PID` 清占端口 → `.env` 存在性/必填 key 检查（findstr，缺失 `goto :error`）→ 清 `src/**/__pycache__` → `.venv` 不存在则 `uv venv .venv && uv sync` → `start "macro" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port %PORT%"`。
3. [2/2] 前端：清端口 → node_modules 不存在则根目录 `pnpm install` → `.env.local` 不存在则 `echo BACKEND_URL=... > .env.local` → `start "Macro App" cmd /k "pnpm dev"`。
4. 尾部输出 Service URLs + `goto :eof` / `:error` 分支。

（fund-select 用的是分离式 `start-fund-select-backend.bat` + `start-fund-select-frontend.bat` 两个脚本；housing 若一个脚本够用，仿 macro 合一式。）

新 `start-housing-dev.bat` 需要的后端 env 检查项：参考源项目，后端运行时本身不需要高德 key（REST key 只在采集脚本 `_gaode_config.py`）；前端需要 `NEXT_PUBLIC_GAODE_MAP_KEY` + `NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY`（build/dev 时 inline）。

## B6. /map 前缀与端口冲突检查

### nginx 路由（`nginx/web.conf`）

现有 location 全集：`= /`（聚合页 L49-52）、`/dividend/_next/static/`、`/douyin/_next/static/`、`/rss/_next/static/`、`/_next/static`、`/dividend/`、`/douyin`、`/api/dividend/`、`/api/douyin/`、`/api/aweme/`、`/rss/api/rss-relay/`、`= /rss/`、`/rss`、`/macro/_next/static/`、`/macro`、`/api/macro/`、`/funds/_next/static/`、`/funds`、`/api/funds/`。

- **`/map` 与 `/api/map` 均未被占用，无冲突**（`/map` 也不是任何现有 location 的子路径；`/macro` 与 `/map` 互不前缀）。
- 需要新增 3 段 location（仿 macro，web.conf L177-206 是完整模板）：
  1. `/map/_next/static/` → `proxy_pass http://housing_frontend/map/_next/static/`（basePath 前缀必须带上）
  2. `/map`（不带尾斜杠，避免 trailingSlash redirect loop）→ 原样转发前端
  3. `/api/map/` → `rewrite ^/api/map/(.*)$ /api/$1 break; proxy_pass http://housing_backend`（剥前缀直转后端；后端 router prefix 须为 `/api`）
- upstream 块两行（仿 L35-38）+ 聚合页 HTML（L51）追加 `/map/` 链接。

### 端口分配现状

| 用途 | 已占用 | 空闲可用 |
|---|---|---|
| 后端 | 8092 dividend、8093 douyin、8094 macro、8095 fund-select + rss-relay（各自容器内） | **8096** 起空闲 |
| 前端 | 3001 macro、3003 dividend、3004 douyin、3005 fund-select、3006 rss-relay | **3002、3007** 起空闲 |

### 其他需同步更新的部署配置

- `docker-compose.nas.yml`：新增 housing-map-backend / housing-map-frontend 两个 service + named volumes + 头部网络路由注释。
- `scripts/deploy-nas.sh`：target 映射（L155-157）、`all` 服务列表（L168）、buildx context 映射（L182-186 需加 `housing-map-frontend) echo "apps/housing-map:apps/housing-map/Dockerfile:housing-map-frontend"`）、帮助文本。
- `.gitignore`：追加 `backend/housing-map/data/`（若数据不入库）。
- 根 `CLAUDE.md`：项目结构图与常用命令需补 housing-map 条目（实施任务范围）。

## Caveats / Not Found

- compose 中 rss-relay-backend 与 fund-select-backend 都用 8095（不同容器不冲突）；housing-map 选 8096 是惯例顺延，无强制约束。
- `.trellis/spec/backend/` 下无 housing-map 相关 spec（现有 dividend-select/douyin-processor/fund-select/global-macro-fin 四个目录），新服务 spec 由实施阶段的 update-spec 流程补。
- nginx web.conf 由 NAS 上 nginx 容器 bind mount 仓库文件（deploy-nas.sh L20-23 注释），改 web.conf 后 `./scripts/deploy-nas.sh nginx` reload 即生效。
