# New Service Onboarding Contract（新服务接入 monorepo 契约）

> 来源：09-18-migrate-binjiang-housing-map 迁移任务。第 6 组服务 housing-map（前端 3007 / 后端 8096）按此契约接入，本文是该契约的权威表述。

## 1. Scope / Trigger

新增一组前后端服务（或迁移外部项目进来）时：涉及 nginx 路由、compose 编排、端口分配、密钥接线、数据卷——全部是 infra/cross-layer 契约，必须按本文逐项落位，禁止只建代码目录。

## 2. Signatures（固定接入点）

| 接入点 | 契约 |
|--------|------|
| 前端目录 | `apps/<name>/`，package name `<name>-frontend`，端口顺延（已用 3001/3003-3007，下一个 3008） |
| 后端目录 | `backend/<name>/`（FastAPI + uv，`[tool.uv] package=false`），端口顺延（已用 8092-8096，下一个 8097） |
| URL 前缀 | basePath `/<name>`（或用户指定的短名）；API 前缀 `/api/<name>/*` |
| nginx | `nginx/web.conf`：upstream ×2 + location ×3（见 §4） |
| compose | `docker-compose.nas.yml`：service ×2 + named volumes + 头部注释三处同步 |
| 部署脚本 | `scripts/deploy-nas.sh`：target 映射 / all 列表 / buildx 映射 / 帮助文本 4 处 |
| 启动脚本 | `scripts/start-<name>-dev.bat`，模板 = start-macro-dev.bat（合一式） |
| 文档 | `CLAUDE.md` 目录树+命令、`DOCKER_DEPLOY.md` 路由表 |
| .gitignore | `backend/<name>/data/` + 秘密文件（如 `scripts/_gaode_config.py`） |

## 3. Contracts

### 3.1 纯前端无 BFF 模式（macro 模式，新服务默认）

前端直接 `fetch('/api/<name>/...')`，本地 dev 用 next.config rewrites 代理，生产 nginx 直转：

```js
// apps/<name>/next.config.js
const nextConfig = {
  output: 'standalone',
  basePath: '/<name>',
  async rewrites() {
    return [{
      source: '/api/<name>/:path*',
      destination: `${process.env.<NAME>_API_ORIGIN || 'http://localhost:<backend_port>'}/api/:path*`,
      basePath: false, // 必须：否则 source 会变成 /<name>/api/<name>/...
    }];
  },
};
```

后端 router 前缀必须 `/api`（`include_router(router, prefix="/api")`），nginx 剥 `/api/<name>` 后正好对上。前端 compose 只设 `NEXT_PUBLIC_API_BASE_URL=/`。

**BFF catch-all（fund-select 模式）仅当需要二进制透传/容器内转发时才用**；NAS 上一律 nginx 直转。

### 3.2 NEXT_PUBLIC_* 密钥接线

NEXT_PUBLIC_* 是 build-time inline，必须走 Dockerfile `ARG` + compose `build.args` + 根 `.env`：

```yaml
# docker-compose.nas.yml
build:
  context: ./apps/<name>
  args:
    NEXT_PUBLIC_SOME_KEY: ${SOME_KEY:-}   # 根 .env 提供（已 gitignore）
```

```dockerfile
# Dockerfile builder 阶段
ARG NEXT_PUBLIC_SOME_KEY
ENV NEXT_PUBLIC_SOME_KEY=$NEXT_PUBLIC_SOME_KEY
```

运行时 env 挂 runtime 环境变量改不了它——改 key 必须 rebuild。

### 3.3 静态数据 volume seed 模式（后端带只读数据文件时）

```dockerfile
COPY data ./data        # 数据进镜像 /app/data
```
```yaml
volumes:
  - <name>-data:/app/data   # named volume 首次挂载为空时，Docker 自动把镜像内内容 seed 进卷
```

零初始化代码：首启自动灌数据，之后 refresh 写入持久化，改数据文件需 rebuild + 删卷（`docker volume rm <name>-data`）。

> **Warning**：数据目录能否 gitignore 取决于数据来源。运行时生成/可经 API 拉取的数据（fund-select/macro 模式）→ gitignore；**静态快照数据（无运行时获取路径，如 housing-map 的爬取快照）必须入 git**——NAS 部署链路是 `git pull` → `docker build`，gitignore 的数据永远到不了 NAS，build 时 `COPY data` 直接失败（2026-09-18 housing-map 首次 NAS 部署实测踩坑）。只 ignore 运行时会重写的派生产物（`*.bak.*`、人读 CSV）。

## 4. nginx location 三件套（模板）

```nginx
# ① 静态资源：proxy_pass URI 必须含完整 basePath，否则前端 404
location /<name>/_next/static/ {
    proxy_pass http://<name>_frontend/<name>/_next/static/;
    proxy_set_header Host $host;
    proxy_cache_valid 200 365d;
    add_header Cache-Control "public, immutable";
}

# ② 页面：location 与 proxy_pass 都不带尾斜杠，否则 trailingSlash redirect loop（/<name> ↔ /<name>/）
location /<name> {
    proxy_pass http://<name>_frontend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# ③ API：rewrite 剥前缀直转后端（upstream 名形式 proxy_pass 不做 URI 替换）
location /api/<name>/ {
    rewrite ^/api/<name>/(.*)$ /api/$1 break;
    proxy_pass http://<name>_backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

upstream 两行（resolve 防 compose 重启 IP 漂移 → 502）：

```nginx
upstream <name>_backend  { zone <name>_backend  64k; server <name>-backend:<port>  resolve; keepalive 16; }
upstream <name>_frontend { zone <name>_frontend 64k; server <name>-frontend:<port> resolve; keepalive 16; }
```

server 名必须与 compose `container_name` 一致。首页聚合页（`location = /` 单行 HTML）追加入口链接。

## 5. Validation & Error Matrix

| 检查 | 命令 | 失败含义 |
|------|------|----------|
| compose 语法 | `docker compose -f docker-compose.nas.yml config --quiet` | YAML/service 引用错误 |
| nginx 语法 | `docker run --rm -v nginx/web.conf:/etc/nginx/conf.d/web.conf:ro nginx nginx -t`（或 NAS 上 `deploy-nas.sh nginx`，内含 nginx -t 失败不 reload） | location/upstream 语法错误 |
| 部署脚本 | `bash -n scripts/deploy-nas.sh` | 映射表语法错误 |
| 后端 | `uv sync && python -m pytest tests/ -v` + curl `/api/health` | 移植/依赖错误 |
| 前端 | `pnpm build`（standalone 产物必须成功） | basePath/依赖错误 |
| 秘密 | `git status --porcelain` + `git check-ignore <秘密文件>` | 秘密文件待提交 = 事故 |

## 6. Good/Base/Bad Cases

- **Good**：housing-map——按上表 9 个接入点逐项落位，build/compose/deploy 一次通过
- **Base**：仅后端服务（无前端）——跳过前端接入点，nginx 只加 location ③
- **Bad**：只建 `apps/<name>` + `backend/<name>` 目录、改代码不碰 nginx/compose/deploy 脚本——本地能跑、NAS 上 404/502，且 `deploy-nas.sh all` 漏掉新服务

## 7. Tests Required

- 后端：API 集成测试（health 200、主端点结构键齐全、total>0）；移植类服务加同源比对（源实现 vs 新实现同数据跑一遍，断言 total/评分 0 差异）
- compose/脚本：§5 的静态校验命令进 check 流程
- 秘密：提交前 `git status` 无 `data/`、`_gaode_config.py`、`.env*` 类路径

## 8. Wrong vs Correct

**Wrong**（前端 fetch 带 basePath 前缀）：
```ts
fetch('/map/api/communities')   // nginx location /api/map 匹配不上 → 404
```

**Correct**：
```ts
fetch('/api/map/communities')   // 绝对路径与 basePath 无关；dev 走 rewrites、生产走 nginx
```

**Wrong**（数据放 `apps/<name>/src` 里随前端打包）：
数据文件混进前端构建产物，refresh 无法更新，且绕过后端数据卷契约。

**Correct**：数据归后端 `data/` + volume seed（§3.3），前端只经 API 消费。

## 9. 移植类迁移补充（gotcha）

> **Warning**：从外部仓库迁移服务时，数据文件只迁运行时最小集（先用 grep 找出被 data-loader/API 引用的文件），raw 中间产物留在源仓库——35MB 目录迁移后实际只引用 10.6MB。评分/清洗逻辑移植后必须做同源比对（起两个服务同一份断言），这是移植正确性的唯一硬证据。
