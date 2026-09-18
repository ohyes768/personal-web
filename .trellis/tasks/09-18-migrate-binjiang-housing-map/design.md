# Design: 迁移滨江购房地图为 personal-web 新服务

依据：prd.md + research/（source-api-analysis.md、data-inventory.md、repo-conventions.md）

## 1. 总体架构

```
nginx /map/*        → housing-map-frontend:3007（Next.js 16.2.6, basePath=/map, 纯前端无 BFF）
nginx /api/map/*    → housing-map-backend:8096（FastAPI，rewrite 剥前缀 → /api/*）
                         │
                         ├── src/services/data_loader.py   读 data/（11 个静态 JSON/JSONL）
                         ├── src/services/scoring.py       四维评分移植
                         ├── src/services/transit.py       地铁线路几何裁剪
                         ├── src/core/boundary.py          滨江区 334 点边界 + isInBinjiang
                         ├── src/api/routes.py             communities/score/transit/refresh/health
                         ├── src/services/refresh.py       asyncio spawn 采集脚本
                         └── scripts/                      15 个采集脚本整体迁移（纯标准库）
```

本地 dev：前端 next.config.js rewrites 把 `/api/map/*` 代理到 `localhost:8096/api/*`（basePath:false），与 nginx 生产剥前缀行为对齐（macro 模式，research B3）。

## 2. 关键设计决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | 数据随镜像 COPY 到 `/app/data`，compose 挂 named volume `housing-map-data:/app/data` | Docker 首次挂空 named volume 会自动 seed 镜像内内容——静态数据免初始化脚本，refresh 写入又持久化（对齐 fund-select volume 模式，零额外代码） |
| D2 | data/ 只迁运行时 11 个文件（10.6 MB），raw 中间产物不迁 | 轮廓/线路再生成依赖 Overpass raw（12 MB+），属一次性快照场景；raw 留在源仓库。接受"再生成管线不可用"限制（脚本仍迁，输入数据不在） |
| D3 | 边界 334 点双端各自持有：后端 `core/boundary.py`（transit 裁剪）+ 前端保留 `binjiang-boundary.ts`（POI 围栏） | 源项目即双端使用；不改造成 API 输出，减少迁移变量 |
| D4 | `/api/score` 保留移植 | 与 communities 共享组装逻辑，边际成本低；保持与源行为完全对齐 |
| D5 | refresh 用 FastAPI 进程内单例 job 状态 + `asyncio.create_subprocess_exec` | 源 Next.js 即单进程单例（research A1.4）；容器单实例部署，无并发问题 |
| D6 | scripts 整体迁移（15 个 py + `_gaode_config.py` 加入 .gitignore），`fetch_property_type_cdp.js` 不迁 | 4 个脚本 import fetch_tmsf_price_snapshot 共享函数；cdp.js 需 Node+浏览器，已被 py 版替代 |
| D7 | 前端类型与纯函数（types.ts 的 getDisplayPrice/getPriceColor/getSchoolLevel、MOCK_COMMUNITIES）保留在前端 | page.tsx 直接 import；评分在后端算，前端只做展示辅助 |
| D8 | FastAPI 返回结构与源 Next.js 完全一致（含 `success/data/total/source/transit` 字段名） | 前端零改动消费；验收抽样比对 |

## 3. 接口契约（与源对齐）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | `{status:"ok"}` |
| `/api/communities` | GET | `{success, data: Community[], total, source:"real"\|"mock", transit:{routes,stops}}`；空数据兜底 MOCK_COMMUNITIES |
| `/api/score` | GET | query: id?、{location,amenity,product,market}Weight?（默认 30/30/25/15）；单/批量两种返回 |
| `/api/transit` | GET | `{success, data:{routes[{id,ref,name,colour,path}],stops[{name,lng,lat}]}, meta:{route_count,stop_count,boundary_points}}`；线路几何截断（segBoundaryIntersect + clipToBinjiang 移植） |
| `/api/refresh` | GET/POST/DELETE | GET=job 状态（phase: idle/fetching/merging/done/error/cancelled）；POST ?limit=N（≤500，0=全量）spawn `scripts/fetch_tmsf_price_snapshot.py --community-id ... --output-dir <data> --sleep 1.2`；DELETE=kill 子进程 |

移植必带逻辑（细节见 research/source-api-analysis.md）：
- 脏数据过滤（路名后缀正则、EXCLUDED_COMMUNITIES）、水电片区合并（primaryId=453982737/fallbackId=453982238/dropIds×4）
- 车位比 `parking_spots/households`、价格口径 `price_type==='monthly_deal_avg_latest'`
- data-loader 清洗：地铁站名/医院（SKIP+后缀剥离+别名）/学校（锚点截断）清洗、POI_BOUNDS 围栏、deduplicatePOIs、mergePrefixNames、coordinates 错区防护、price_snapshots 口径优先级
- scoring 四维公式：区位（≤400m 段+衰减段）/配套（类型权重+封顶+缺类 10 分+学段折算）/产品力（5 子项缺侧重归一）/市场面；总分加权 clamp
- refresh 数据安全：备份 → 脚本覆盖 jsonl → 退出码 0 合并（新记录在前、按 community_id|price_type 去重、未抓到保旧价）→ 重写 CSV（utf-8-sig）；`[ok]/[error]` stdout 计数

## 4. 目录结构

```
backend/housing-map/
├── pyproject.toml          # fastapi/uvicorn/pydantic/python-dotenv + pytest(dev)；[tool.uv] package=false
├── .env.example            # HOUSING_PORT=8096 / LOG_LEVEL=INFO
├── Dockerfile              # 仿 fund-select：python:3.12-slim + uv sync --frozen + COPY data/ + HEALTHCHECK
├── data/                   # 11 个运行时文件（gitignore，随镜像 COPY）
├── scripts/                # 15 个 py + _gaode_config.py（gitignore，提供 _gaode_config.py.example）
├── src/
│   ├── main.py             # lifespan + CORS + include_router(prefix="/api")
│   ├── api/routes.py       # 5 组端点
│   ├── api/models.py       # Pydantic 响应模型（宽松：dict 直传为主，强类型仅入参）
│   ├── core/boundary.py    # 334 点 + isInBinjiang（移植 binjiang-boundary.ts）
│   ├── services/data_loader.py   # 11 文件加载 + 全部清洗规则
│   ├── services/scoring.py       # 四维评分
│   ├── services/transit.py       # 线路裁剪
│   └── services/refresh.py       # job 单例 + subprocess 管理
└── tests/                  # scoring 公式 case、data_loader 清洗、API 集成（health/communities 结构）
```

前端 `apps/housing-map/`：源 `web/` 全量复制后改造——删 `src/app/api/`、next.config.js（standalone+basePath=/map+rewrites）、package.json（name=housing-map-frontend、端口 3007）、Dockerfile（仿 fund-select 三阶段）、`.env.local`（2 个 NEXT_PUBLIC 高德 key）。page.tsx 5 处 fetch 改 `/api/map/*`（research A4 清单）。

## 5. 部署改动清单（全量）

| 文件 | 改动 |
|------|------|
| nginx/web.conf | +2 upstream（housing_map_backend:8096 / housing_map_frontend:3007）；+3 location（`/map/_next/static/` URI 替换含 basePath、`/map` 无尾斜杠、`/api/map/` rewrite 剥前缀）；聚合页 HTML + `🏠 滨江购房地图` 链接 |
| docker-compose.nas.yml | +housing-map-backend（8096、healthcheck、volume housing-map-data:/app/data、HOUSING_PORT）+housing-map-frontend（3007、build args NEXT_PUBLIC_GAODE_MAP_KEY/NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY、depends_on backend healthy）+volumes 声明+头部注释 |
| scripts/deploy-nas.sh | target 映射（L155-157）、all 列表（L168）、buildx context 映射（L182-186）、帮助文本 |
| .gitignore | +`backend/housing-map/data/`、`backend/housing-map/scripts/_gaode_config.py` |
| scripts/start-housing-dev.bat | 仿 start-macro-dev.bat 合一式：后端 uvicorn 8096 + 前端 pnpm dev 3007 |
| CLAUDE.md | 项目结构图 + 常用命令补 housing-map 条目 |

compose 环境变量：根 `.env` 需新增 `GAODE_MAP_KEY`（前端 build arg）、`GAODE_MAP_SECURITY_KEY`（前端 build arg）；后端无必须 key（采集脚本 key 在 `_gaode_config.py`，随 volume/镜像分发，不入 git）。

## 6. 兼容性 / 回滚

- 全部为增量改动：不动其他 5 组服务的 nginx location、compose service、端口。回滚 = git revert 本次提交 + NAS 上 `docker compose -f docker-compose.nas.yml up -d --remove-orphans`。
- Next.js 16 注意事项：web/AGENTS.md 提示有 breaking changes；前端迁移以"复制 + 最小改动"为准，不重构 page.tsx（650 行保持原样，仅改 fetch 路径）。
- 源仓库 hangzhou-housingmap 保持只读，纯复制迁移。

## 7. 验证策略

1. 后端：`python -m pytest tests/ -v`（评分公式 case 用 research A2 公式直接断言：400m 边界、缺类 10 分、学段折算、市场面 dealCount≤0→30、全缺失→50 等）
2. 移植一致性抽样：本地同起源 Next.js dev 与 FastAPI，`/api/communities` 比对 total、首个小区 score、`/api/transit` 比对 route_count/stop_count
3. 前端：`pnpm build` 通过；`pnpm dev` 地图页点位/价格色阶/评分弹窗正常
4. nginx：`docker run --rm -v nginx/web.conf nginx -t` 或 NAS 部署时验证
