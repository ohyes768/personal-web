# Implement: 迁移滨江购房地图为 personal-web 新服务

执行顺序：阶段 1 → 2 → 3 → 4（阶段 3 与 1/2 可并行，但建议顺序执行避免 git 冲突）。每阶段结束跑对应验证命令。

## 阶段 1：后端数据与核心逻辑移植

- [ ] 1.1 建 `backend/housing-map/` 骨架：pyproject.toml（fastapi/uvicorn[standard]/pydantic/python-dotenv，dev: pytest/pytest-cov；`[tool.uv] package=false`）、.env.example、.gitignore 条目（仓库根：`backend/housing-map/data/`、`backend/housing-map/scripts/_gaode_config.py`）
- [ ] 1.2 迁移数据：从 `F:/personal-projects/hangzhou-housingmap/data/` 复制 11 个运行时文件（清单见 research/data-inventory.md 表格）到 `backend/housing-map/data/`
- [ ] 1.3 迁移脚本：复制 `scripts/` 全部 .py + `_gaode_config.py`（15 个 py）；提供 `_gaode_config.py.example`；不迁 `fetch_property_type_cdp.js`；脚本保持原样（纯标准库，不改逻辑）
- [ ] 1.4 移植 `src/core/boundary.py`：binjiang-boundary.ts 的 334 点 + isInBinjiang（射线法）
- [ ] 1.5 移植 `src/services/data_loader.py`：11 文件加载 + 全部清洗规则（research A2 清单逐条对照源码 data-loader.ts）
- [ ] 1.6 移植 `src/services/scoring.py`：findNearestStation + 四维公式 + calculateAllScores（对照 scoring.ts 逐行）
- [ ] 1.7 移植 `src/services/transit.py`：segBoundaryIntersect + clipToBinjiang + 线路/站点组装（对照 transit/route.ts L49-153）
- [ ] 1.8 写 pytest：scoring 公式关键 case（400m 边界、缺类 10 分、学段折算 ÷1.4/÷0.6、市场面 dealCount≤0→30、全缺失→50、权重重归一）、data_loader 清洗（地铁名后缀、POI_BOUNDS、口径优先级）、boundary isInBinjiang 采样点

验证：`cd backend/housing-map && uv sync && python -m pytest tests/ -v` 全绿

## 阶段 2：后端 API 路由 + refresh

- [ ] 2.1 `src/api/routes.py`：GET /health、GET /communities（组装逻辑含脏数据过滤/片区合并/车位比/价格口径 + calculateScore + 空数据 MOCK 兜底）、GET /score（单/批量 + 权重覆盖）、GET /transit、GET/POST/DELETE /refresh
- [ ] 2.2 `src/services/refresh.py`：job 单例（running/phase/total/processed/okCount/errorCount/startedAt/finishedAt/error/result）、POST 启动（备份 jsonl → asyncio.create_subprocess_exec python scripts/fetch_tmsf_price_snapshot.py ... --sleep 1.2）、[ok]/[error] stdout 计数、退出码 0 合并去重 + CSV 重写（utf-8-sig）、DELETE kill 子进程
- [ ] 2.3 `src/main.py`：load_dotenv、lifespan、CORS、`include_router(prefix="/api")`
- [ ] 2.4 `src/api/models.py`：入参 Pydantic 模型（refresh limit、score weights）；响应用 dict 保持与源字段名一致（D8）
- [ ] 2.5 API 集成测试：health 200、communities 返回结构（success/data/total/source/transit 键存在、total>0）、transit meta 键存在、refresh GET 初始 idle
- [ ] 2.6 Dockerfile（仿 fund-select：python:3.12-slim、uv sync --frozen、COPY data/ 到 /app/data、HEALTHCHECK curl /api/health、CMD uvicorn ${HOUSING_PORT:-8096}）

验证：`uvicorn src.main:app --port 8096` 起服务，curl /api/health、/api/communities、/api/transit 冒烟；`python -m pytest tests/ -v` 全绿

## 阶段 3：前端迁移

- [ ] 3.1 复制 `F:/personal-projects/hangzhou-housingmap/web/` → `apps/housing-map/`（src、public、配置文件；不带 node_modules/.next/tsconfig.tsbuildinfo/AGENTS.md）
- [ ] 3.2 删 `src/app/api/` 四个路由目录及空目录（geocode/pois/dashboard、components/community、components/dashboard）
- [ ] 3.3 next.config.js：`{ output:'standalone', basePath:'/map', async rewrites(){ return [{ source:'/api/map/:path*', destination: `${process.env.HOUSING_API_ORIGIN || 'http://localhost:8096'}/api/:path*`, basePath:false }] } }`（macro 模式）
- [ ] 3.4 package.json：name=housing-map-frontend、dev/start 端口 3007、依赖保持 next 16.2.6/react 19.2.4/tailwind v4
- [ ] 3.5 改 5 处 fetch（research A4 清单）：page.tsx L12→/api/map/communities、L237→/api/map/transit、L289/302/309→/api/map/refresh；其余代码不动
- [ ] 3.6 Dockerfile：仿 apps/fund-select（node:20-alpine 三阶段、standalone 三段拷贝、PORT=3007）；build args 接 NEXT_PUBLIC_GAODE_MAP_KEY / NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY
- [ ] 3.7 .env.local 本地模板（2 个高德 key，不入库）

验证：`cd apps/housing-map && pnpm install && pnpm build` 成功；`pnpm dev`（配合后端 8096）地图页点位/评分/弹窗正常

## 阶段 4：部署配置 + 文档

- [ ] 4.1 nginx/web.conf：+2 upstream、+3 location（`/map/_next/static/` proxy_pass 带 `/map/_next/static/`、`/map` 无尾斜杠、`/api/map/` rewrite 剥前缀）、聚合页加 `🏠 滨江购房地图 → /map`（插在合适位置，保持单行 HTML）
- [ ] 4.2 docker-compose.nas.yml：+housing-map-backend（expose 8096、HOUSING_PORT、volume housing-map-data:/app/data、healthcheck /api/health、app-net）+housing-map-frontend（ports 127.0.0.1:3007:3007、NEXT_PUBLIC_API_BASE_URL=/、build args 两个高德 key 从根 .env 取、depends_on backend healthy）+ volumes: housing-map-data + 头部注释路由说明（/map/* → 3007、/api/map/* → 8096）
- [ ] 4.3 scripts/deploy-nas.sh：target 映射、all 服务列表、buildx context 映射、帮助文本（research B6 L155/168/182-186 三处）
- [ ] 4.4 scripts/start-housing-dev.bat：仿 start-macro-dev.bat（后端 8096 uvicorn --reload + 前端 3007 pnpm dev，端口清理 + .env 检查）
- [ ] 4.5 CLAUDE.md：项目结构图加 housing-map 前后端两行 + 常用命令节加启动命令
- [ ] 4.6 DOCKER_DEPLOY.md / README.md 如有服务清单/端口表同步一行

验证：nginx 语法 `docker run --rm -v $(pwd)/nginx/web.conf:/etc/nginx/conf.d/web.conf nginx nginx -t`（或等效审查）；`docker compose -f docker-compose.nas.yml config` 语法校验

## 阶段 5：端到端验证（check 阶段）

- [ ] 5.1 后端 pytest 全绿 + uvicorn 冒烟
- [ ] 5.2 前端 build 成功 + dev 页面验证（经 rewrites 打到 8096）
- [ ] 5.3 移植一致性抽样：total 数量、transit route_count/stop_count 与源项目 dev 输出比对（如源环境可起）
- [ ] 5.4 grep 全仓库无硬编码高德 key；compose 变量与 .env 注释对齐
- [ ] 5.5 trellis-check 全量检查

## 回滚点

- 每阶段独立可回退：阶段 1-2 只新增 backend/housing-map/；阶段 3 只新增 apps/housing-map/；阶段 4 改共享文件（nginx/compose/deploy/.gitignore/CLAUDE.md）——共享文件改动集中在最后一批，出问题 git checkout 单文件即恢复
