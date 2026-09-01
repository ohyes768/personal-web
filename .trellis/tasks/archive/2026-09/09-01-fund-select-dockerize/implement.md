# fund-select Docker 化 — 执行计划

> PRD 见 `prd.md`；技术决策见 `design.md`。本文是落地清单。

## 0. 前置确认（实施前必做）

- [ ] `prd.md` / `design.md` 已通过用户 review
- [ ] `task.py start` 已执行（status → in_progress）
- [ ] 当前分支 / 工作区干净（personal-web 这边不动；改动全在 fund-select）

## 1. 文件清单（fund-select 仓 6 新 + README 追加；personal-web 仓 2 改 + 1 改 README）

| # | 仓库 | 路径 | 性质 | 行数估算 |
|---|---|---|---|---|
| 1 | fund-select | `backend/Dockerfile` | 新建 | ~50 |
| 2 | fund-select | `backend/.dockerignore` | 新建 | ~10 |
| 3 | fund-select | `frontend/Dockerfile` | 新建 | ~35 |
| 4 | fund-select | `frontend/.dockerignore` | 新建 | ~10 |
| 5 | fund-select | `docker-compose.yml` | 新建 | ~70 |
| 6 | fund-select | `.env.example` | 新建 | ~10 |
| 7 | fund-select | `README.md` | **追加**「Docker 部署」小节 | +30 行 |
| 8 | personal-web | `nginx/web.conf` | **改**：新增 2 upstream + 3 location + 聚合页 1 行 | +40 行 |
| 9 | personal-web | `docker-compose.nas.yml` | **改**：新增 2 service + 4 volume + 头部注释 | +60 行 |
| 10 | personal-web | `CLAUDE.md` | **改**：补 fund-select 开发命令 | +6 行 |

## 2. 实施顺序（按依赖关系）

```
Step 1: backend/Dockerfile + backend/.dockerignore
   ↓
Step 2: frontend/Dockerfile + frontend/.dockerignore
   ↓
Step 3: docker-compose.yml + .env.example
   ↓
Step 4: README.md 追加「Docker 部署」小节
   ↓
Step 5: nginx/web.conf 新增 fund-select 路由
   ↓
Step 6: docker-compose.nas.yml 合并 fund-select service
   ↓
Step 7: CLAUDE.md 补 fund-select 开发命令
   ↓
Step 8: 端到端冒烟（fund-select 自带 compose 跑一遍 → curl 验证）
   ↓
Step 9: 检查清单 + 双仓 git commit + task.py finish + archive
```

## 3. Step 1 — 后端 Dockerfile

**文件**：`F:/personal-projects/fund-select/backend/Dockerfile`

**模板**（参照 `backend/dividend-select/Dockerfile`，但要保留 fund-select 特定差异）：
- `WORKDIR /app`
- apt 阿里云源（debian bookworm：`/etc/apt/sources.list.d/debian.sources`）
- 装 `curl` + `nodejs` + `tzdata`（slim 不带 zoneinfo）
- `ENV TZ=Asia/Shanghai`
- pip 清华源
- `pip install uv`
- `COPY pyproject.toml uv.lock ./`
- `COPY config ./config`
- `COPY src ./src`
- `RUN uv sync --frozen --no-dev`
- `ENV PATH="/app/.venv/bin:$PATH"`
- `RUN mkdir -p data logs cache`
- `EXPOSE 8095`
- HEALTHCHECK 命中 `/api/funds/health`
- CMD 走 `uvicorn src.main:app --host 0.0.0.0 --port ${SERVER_PORT:-8095}`

**校验**：
```bash
cd F:/personal-projects/fund-select
docker build -t fund-select-backend:test -f backend/Dockerfile backend/
# 期望：success，无 ERROR
docker run --rm -d -p 8095:8095 --name fs-b-test fund-select-backend:test
curl http://localhost:8095/api/funds/health
# 期望：{"status":"ok",...} 或类似 JSON
docker stop fs-b-test
```

**`.dockerignore`** 排除：
- `.venv/` `__pycache__/` `*.pyc` `tests/` `.pytest_cache/`
- `data/` `logs/` `cache/`（避免把本地数据打进镜像）
- `.env` `.env.local`（避免泄漏本地密钥）
- `.git/` `.gitignore` `README.md`（与运行无关）
- `*.egg-info/` `dist/` `build/`

## 4. Step 2 — 前端 Dockerfile

**文件**：`F:/personal-projects/fund-select/frontend/Dockerfile`

**模板**（照搬 `apps/dividend/Dockerfile`，只改端口 3003→3005）：
- 阶段 1 `deps`：`node:20-alpine` + `npm install -g pnpm` + `pnpm install --frozen-lockfile`（cache mount）
- 阶段 2 `builder`：拷 `node_modules` + `.` + `pnpm build`
- 阶段 3 `runner`：user `nextjs` (uid=1001) + 拷 `.next/standalone` + `.next/static` + `public/`
- `EXPOSE 3005`、`ENV PORT=3005`、`ENV HOSTNAME=0.0.0.0`
- `CMD ["node", "server.js"]`

**校验**：
```bash
cd F:/personal-projects/fund-select
docker build -t fund-select-frontend:test -f frontend/Dockerfile frontend/
# 期望：success
docker run --rm -d -p 3005:3005 --name fs-f-test fund-select-frontend:test
curl -I http://localhost:3005/funds
# 期望：HTTP/1.1 200
docker stop fs-f-test
```

**`.dockerignore`** 排除：
- `node_modules/` `.next/` `out/` `dist/` `build/`
- `.git/` `.env*` `.npmrc`（注意：`.npmrc` 不排，pnpm 装包时要读私有 registry 配置，但 fund-select 用默认 registry，可以排；要谨慎，先排保险点）
- 测试 / coverage 报告目录
- `*.log` `.DS_Store` `.vscode/` `.idea/`

## 5. Step 3 — docker-compose.yml

**文件**：`F:/personal-projects/fund-select/docker-compose.yml`

**关键约束**：
- 2 service：`fund-select-backend` + `fund-select-frontend`
- backend：`build: ./backend`，`expose: ["8095"]`，healthcheck 走 `/api/funds/health`
- frontend：`build: ./frontend`，`ports: ["127.0.0.1:3005:3005"]`，env 注入 `BACKEND_URL`
- volumes：`fund-select-data` / `fund-select-cache` / `fund-select-config` / `fund-select-logs`
- network：声明 `app-net` (bridge)，**不** 标 external
- frontend `depends_on` backend `condition: service_healthy`
- `restart: unless-stopped`

**`.env.example`** 内容：
```
# fund-select 部署环境变量样例；复制为 .env 后按需修改
SERVER_PORT=8095
LOG_LEVEL=INFO
TZ=Asia/Shanghai
```

**校验**：
```bash
cd F:/personal-projects/fund-select
docker compose config         # 期望：YAML 合法，无警告
docker compose up -d --build  # 期望：两个 service 都 healthy
docker compose ps             # 期望：State = healthy
```

## 6. Step 4 — README 追加

**文件**：`F:/personal-projects/fund-select/README.md`

**追加位置**：在「已知限制（v1）」之后追加新小节，**不动**已有内容。

**小节骨架**：
```markdown
## Docker 部署

### 快速开始（NAS / Linux）

\`\`\`bash
cd /path/to/fund-select
cp .env.example .env       # 按需编辑
docker compose up -d --build
\`\`\`

访问：
- 前端：http://localhost:3005/funds
- 后端：http://localhost:8095/api/funds/health

### 数据卷

| Volume | 容器路径 | 内容 |
|---|---|---|
| fund-select-data | /app/data | SQLite funds.db |
| fund-select-cache | /app/cache | akshare / 费率 / 经理表 JSON |
| fund-select-config | /app/config | funds.yaml（31 只名单） |
| fund-select-logs | /app/logs | 应用日志 |

### NAS 部署

假设已与 personal-web 部署在同一 NAS，nginx + docker-compose.nas.yml 已合并：

\`\`\`
https://web.duomi77.cn/funds/         # 前端
https://web.duomi77.cn/api/funds/     # 后端 API
\`\`\`
```

## 7. Step 5 — nginx/web.conf

**文件**：`F:/personal-projects/personal-web/nginx/web.conf`

**改动 1**：在已有 upstream 块（line 36 之后）追加：
```nginx
upstream fund_select_backend  { zone fund_select_backend  64k; server fund-select-backend:8095  resolve; keepalive 16; }
upstream fund_select_frontend { zone fund_select_frontend 64k; server fund-select-frontend:3005 resolve; keepalive 16; }
```

**改动 2**：在文件末尾（macro API 之后，line 204 后）追加 3 个 location：
```nginx
# fund-select 静态资源（basePath='/funds'，参照 /rss/_next/static/）
location /funds/_next/static/ {
    proxy_pass http://fund_select_frontend/funds/_next/static/;
    proxy_set_header Host $host;
    proxy_cache_valid 200 365d;
    add_header Cache-Control "public, immutable";
}

# fund-select 页面（basePath='/funds'，参照 location /rss 不带尾斜杠）
location /funds {
    proxy_pass http://fund_select_frontend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}

# fund-select API（nginx 直转后端，剥 /api/funds 前缀 → /api/<x>，对齐 router prefix）
location /api/funds/ {
    rewrite ^/api/funds/(.*)$ /api/$1 break;
    proxy_pass http://fund_select_backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

**改动 3**：根路径聚合页 HTML（line 49）插入一行 `<a href="/funds/">📈 基金筛选</a>` 在 macro 链接前。

**校验**：
```bash
# 本地用 nginx -t（如有 nginx 二进制），或在 NAS 上 reload 前用：
docker run --rm -v F:/personal-projects/personal-web/nginx:/etc/nginx/conf.d:ro \
    nginx:alpine nginx -t -c /etc/nginx/nginx.conf -g 'include /etc/nginx/conf.d/*.conf;'
# 期望：syntax is ok / test is successful
```

## 8. Step 6 — docker-compose.nas.yml 合并

**文件**：`F:/personal-projects/personal-web/docker-compose.nas.yml`

**改动 1**：文件头部注释块（line 19-29）更新网络路由段，追加：
```
/funds/*        → fund-select-frontend:3005    (basePath = /funds)
/api/funds/* → fund-select-backend:8095/api/*  (nginx 直转后端；fund-select 前端 BFF 仅本地）
```

**改动 2**：在文件末尾 macro-frontend 后（line 250 后）追加 2 个 service：
```yaml
  # ---------------------------------------------------------------------------
  # fund-select 后端（债基筛选，独立仓 F:/personal-projects/fund-select/）
  # ---------------------------------------------------------------------------
  fund-select-backend:
    build:
      context: ../fund-select/backend
    container_name: fund-select-backend
    restart: unless-stopped
    expose:
      - "8095"
    volumes:
      - fund-select-data:/app/data
      - fund-select-cache:/app/cache
      - fund-select-config:/app/config
      - fund-select-logs:/app/logs
    environment:
      - TZ=Asia/Shanghai
      - SERVER_PORT=8095
      - LOG_LEVEL=INFO
    networks:
      - app-net
    healthcheck:
      test: ["CMD", "sh", "-c", "curl -f http://localhost:${SERVER_PORT:-8095}/api/funds/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # ---------------------------------------------------------------------------
  # fund-select 前端（Next.js 15，basePath='/funds'，独立仓 F:/personal-projects/fund-select/）
  # BFF 用 BACKEND_URL 找到后端
  # ---------------------------------------------------------------------------
  fund-select-frontend:
    image: fund-select-frontend:latest
    build:
      context: ../fund-select/frontend
      dockerfile: Dockerfile
    container_name: fund-select-frontend
    restart: unless-stopped
    ports:
      - "127.0.0.1:3005:3005"
    environment:
      - NODE_ENV=production
      - NEXT_PUBLIC_API_BASE_URL=/funds
      - BACKEND_URL=http://fund-select-backend:8095
    networks:
      - app-net
    depends_on:
      fund-select-backend:
        condition: service_healthy
```

**改动 3**：volumes 段（line 263 后）追加：
```yaml
  fund-select-data:
    name: fund-select-data
  fund-select-cache:
    name: fund-select-cache
  fund-select-config:
    name: fund-select-config
  fund-select-logs:
    name: fund-select-logs
```

**校验**：
```bash
cd F:/personal-projects/personal-web
docker compose -f docker-compose.nas.yml config -q   # 期望：0 输出（合法）
docker compose -f docker-compose.nas.yml config | grep -A2 fund-select   # 期望：能看到两 service
```

## 9. Step 7 — personal-web CLAUDE.md 补充

**文件**：`F:/personal-projects/personal-web/CLAUDE.md`

**改动**：在「常用命令」段尾的「后端开发」子段（dividend-select 后）追加 fund-select 后端命令块：
```markdown
# fund-select（独立项目 F:/personal-projects/fund-select/，不在本仓）
cd F:/personal-projects/fund-select/backend
uv sync
python -m pytest tests/ -v
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8095

# fund-select 前端
cd F:/personal-projects/fund-select/frontend
pnpm dev          # 端口 3005，访问 /funds
```

不动「架构说明」「项目概述」段。

## 10. Step 8 — 端到端冒烟

**环境**：本地 Docker Desktop（Windows）+ Linux 容器模式。

**命令清单**：
```bash
cd F:/personal-projects/fund-select

# 1. 干净起
docker compose down -v
docker compose up -d --build

# 2. 等健康
sleep 30
docker compose ps

# 3. 健康检查
curl -s http://localhost:8095/api/funds/health
curl -sI http://localhost:3005/funds

# 4. 数据接口
curl -s "http://localhost:8095/api/funds/screen?min_age=3&min_size_yi=10" | head -c 500

# 5. 容器内部连通性（用 service name）
docker compose exec fund-select-frontend wget -qO- http://fund-select-backend:8095/api/funds/health

# 6. 卷持久化验证
docker compose down       # 不带 -v
docker compose up -d
curl -s "http://localhost:8095/api/funds/screen" | python -c "import sys,json; d=json.load(sys.stdin); print(f'funds={len(d.get(\"items\", d) if isinstance(d, dict) else d)}')"

# 7. 日志确认 scheduler 启动
docker compose logs fund-select-backend | grep -i "scheduler\|服务启动"

# 8. 收尾
docker compose down -v    # 清理
```

**通过标准**：上面 8 步全过，logs 无 ERROR 级。

## 11. Step 9 — 检查清单与提交

**自检 checklist**（逐条勾）：
- [ ] fund-select 仓：6 个新文件 + README diff 全部存在
- [ ] personal-web 仓：nginx/web.conf + docker-compose.nas.yml + CLAUDE.md diff 全部存在
- [ ] `docker compose config` 0 错误（fund-select 自带）
- [ ] `docker compose -f docker-compose.nas.yml config -q` 0 输出（personal-web）
- [ ] Step 8 冒烟 8 步全过
- [ ] `.env.example` 存在；`.gitignore` 已含 `.env`

**双仓提交**：

```bash
# fund-select 仓
cd F:/personal-projects/fund-select
git status
git add backend/Dockerfile backend/.dockerignore \
        frontend/Dockerfile frontend/.dockerignore \
        docker-compose.yml .env.example \
        README.md
git commit -m "feat(deploy): 新增 Dockerfile + docker-compose

- backend: python:3.12-slim + uv sync，healthcheck 命中 /api/funds/health
- frontend: Next.js standalone 多阶段构建，basePath /funds
- compose: 2 service + 4 named volume + app-net
- .env.example + README Docker 部署小节

Refs: .trellis/tasks/09-01-fund-select-dockerize (planning 在 personal-web 仓)"

# personal-web 仓
cd F:/personal-projects/personal-web
git status
git add nginx/web.conf docker-compose.nas.yml CLAUDE.md
git commit -m "feat(nginx): 接入 fund-select 路由 + docker-compose.nas.yml 合并两 service

- nginx/web.conf: 新增 2 upstream (fund_select_backend/frontend) + 3 location
  (静态 /funds/_next/static、页面 /funds、API /api/funds/)；根路径聚合页加链接
- docker-compose.nas.yml: 新增 fund-select-backend (8095) + fund-select-frontend
  (3005) service，4 个 named volume，context 指 ../fund-select/
- CLAUDE.md: 补 fund-select 后端 / 前端开发命令

Refs: .trellis/tasks/09-01-fund-select-dockerize"
```

**Trellis finish**：
```bash
cd F:/personal-projects/personal-web
python ./.trellis/scripts/task.py finish
python ./.trellis/scripts/task.py archive
```

## 12. 回滚点

如果 Step 8 冒烟失败：
1. `docker compose down -v` 清理容器 + 卷
2. 不删除任何文件，先 `git status` 看改了哪些
3. 排查方向：
   - 后端连不上 akshare → 检查容器 DNS / 网络
   - frontend 502 → backend 还没 healthy；延长 start-period
   - scheduler 启动报错 → 检查 `cache/` 权限
   - uvicorn SIGSEGV → 走 `uvicorn-sigsegv-fix` skill 切 gunicorn
   - nginx 502 → 检查 fund-select 容器在 `nginx_nginx-bridge` network 里
4. 修复后从 Step 8 重跑，不重做文件

如果仅 personal-web nginx/compose 报错：
1. `git checkout nginx/web.conf docker-compose.nas.yml CLAUDE.md`
2. 保留 fund-select 仓的 6 个新文件（不互相依赖）

## 13. Follow-up（不在本次范围内）

- [ ] gunicorn + UvicornWorker 替 uvicorn（SIGSEGV 防护）
- [ ] ARM64 多架构镜像（buildx --platform）
- [ ] 自动 push 到私有 registry
- [ ] Healthcheck 加 akshare 探活（不只是 200）
- [ ] 备份脚本：`fund-select-data` 每日 dump
