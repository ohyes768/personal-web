# Research: 源项目 API 与核心逻辑分析（hangzhou-housingmap）

- **Query**: 滨江购房地图迁移 — 调研项 A1-A4（API 路由 / 数据加载与评分 / 高德依赖 / 前端调用点）
- **Scope**: internal（F:/personal-projects/hangzhou-housingmap）
- **Date**: 2026-09-18

## 总览

源项目是单体 Next.js 16.2.6 应用（`web/`），API 路由为 Next Route Handlers，直接读仓库根 `data/` 目录的 JSON/JSONL 文件。数据目录定位方式：`path.join(process.cwd(), '..', 'data')`（web 进程 cwd 是 `web/`，故 data 在仓库根）——迁到 FastAPI 后此路径逻辑需改为 `backend/housing-map/data/`。

坐标系：全项目统一 GCJ-02（高德系）。OSM 原始数据 WGS84 由转换脚本处理，运行时不转换。

---

## A1. API 路由逐个分析

### 1. GET /api/communities（`web/src/app/api/communities/route.ts`）

- **方法/参数**：GET，无 query 参数。
- **依赖数据文件**（经 data-loader，共 11 个）：communities / coordinates / pois / priceSnapshots / propertyTypes / polygons / subwayStations / communityAges / communityAttrs / transitRoutes / transitStops。
- **核心逻辑**：
  1. L7-9 脏数据过滤：路名后缀正则 `(大道|路|街|巷)$` 剔除；排除集合 `EXCLUDED_COMMUNITIES = {'新街镇北塘河'}`（L9）。
  2. L14-21 水电片区合并组：`primaryId='453982737'`（水电社区）借 `fallbackId='453982238'` 的价格/POI；`dropIds` 4 个成员从列表剔除。
  3. L40-44 车位比计算：`parking_spots / households`（两者皆正数才有效，保留 2 位小数）。
  4. L68-116 组装 Community 对象：价格区分口径（`price_type === 'monthly_deal_avg_latest'` → deal_avg_price，否则 listing_avg_price；L74）；`listing_count/deal_count` 用 `??` 保 0（0 是有效数据，L97-99 注释）；`boundary` 取 polygons 的 rings；`nearest_subway` 由 `findNearestStation` 算。
  5. L118-121 对每条记录 `calculateScore(c)` 评分。
- **返回结构**：
  ```json
  { "success": true, "data": Community[], "total": n, "source": "real",
    "transit": { "routes": TransitFeatureCollection, "stops": TransitStopCollection } }
  ```
  注意：`transit` 字段返回的是**原始 GeoJSON FeatureCollection（未裁剪）**，与 /api/transit 的裁剪版不同。前端 page.tsx 只用 /api/transit，不用这个字段。
- **空数据兜底**：communities 为空时返回 `MOCK_COMMUNITIES`（types.ts L131-198），`source: 'mock'`。

### 2. GET /api/score（`web/src/app/api/score/route.ts`）

- **方法/参数**：GET。Query：
  - `id`（可选）：指定小区 ID → 单小区模式。
  - `{location,amenity,product,market}Weight`（可选，int）：覆盖默认权重 30/30/25/15（L11-20，缺省取 `DEFAULT_WEIGHTS`）。
- **依赖数据文件**：communities / coordinates / pois / priceSnapshots / subwayStations / communityAges / communityAttrs（无 polygons/transit）。
- **核心逻辑**：与 communities 路由相同的组装逻辑（但单小区模式 `listing_count/deal_count` 固定 null，L80-81），最后 `calculateScore(communityData, weights)`；批量模式按 `total_score` 降序（L158）。
- **返回结构**：单小区 `{success, data: Community}`；批量 `{success, data: Community[], total, weights}`。
- **重要事实**：前端代码（page.tsx / BinjiangMap.tsx）**从未调用 /api/score**（grep 全 src 无 `api/score` 引用）——评分实际都在 /api/communities 服务端完成。迁移时该端点可低优先或与 communities 合并。

### 3. GET /api/transit（`web/src/app/api/transit/route.ts`）

- **方法/参数**：GET，无参数。
- **依赖数据文件**：直接 fs 读（不经 data-loader）`data/binjiang_transit_routes.geojson` + `data/binjiang_transit_stops.geojson`（L113-119，同样 `cwd/../data` 定位）。
- **核心逻辑**：
  1. L49-69 `segBoundaryIntersect`：线段与滨江区边界交点，参数方程二分 16 次求交（精度约 1 米）。
  2. L76-110 `clipToBinjiang`：多段线裁剪为边界内连续子段（in-out 交替处断开），输出 `number[][][]`（多条子段）。
  3. L126-140 线路：只取 `route === 'subway'` 的 relation，裁剪后每段展成一条 `{id: "<osm_id>-<idx>", ref, name, colour, path}`。
  4. L143-153 站点：`kind === 'subway'` 且 `isInBinjiang(lng, lat)` 严格坐标过滤 → `{name, lng, lat}`。
- **返回结构**：
  ```json
  { "success": true,
    "data": { "routes": [{"id","ref","name","colour","path":[[lng,lat],...]}],
               "stops": [{"name","lng","lat"}] },
    "meta": { "route_count": n, "stop_count": n, "boundary_points": 334 } }
  ```
- **注意**：`docs/DATA_SOURCES.md` 第四节写"线路任一节点在滨江内则保留（不强行截短几何）"，但代码实际是**几何截断成子段**（L124 注释"先裁剪到滨江区边界 (几何截断, 不只是选不选)"）。以代码为准，文档滞后。

### 4. /api/refresh（`web/src/app/api/refresh/route.ts`）—— 价格快照刷新任务

- **方法**：
  - `GET`：返回模块级单例 job 状态 `{running, phase, total, processed, okCount, errorCount, startedAt, finishedAt, error, result}`（L24-35, L95-97）。phase 取值 `idle|fetching|merging|done|error|cancelled`。
  - `POST ?limit=N`（N 上限 500，测试用；0=全量）：启动刷新（L99-190）。
  - `DELETE`：kill 子进程（L192-198），数据不动。
- **依赖**：`loadCommunities()` 取全量小区 ID；spawn `python ../scripts/fetch_tmsf_price_snapshot.py --community-id <id>... --output-dir <dataDir> --sleep 1.2`（L134），PYTHONIOENCODING=utf-8。
- **数据安全流程**（L7-16 注释 + 实现）：
  1. 启动前备份 `price_snapshots.jsonl` → `price_snapshots_<YYYY-MM-DD>.bak.jsonl`（L115-119）。
  2. 脚本抓完一次性覆盖 jsonl；退出码 0 时合并：新记录在前，按 `community_id|price_type` 去重，未抓到的保留旧价（`mergeSnapshots` L68-77）。
  3. 重写人工查看用 CSV（utf-8-sig，字段清单 L18-22）（L80-93）。
  4. 失败/中止：原文件未动。
- **进度协议**：脚本 stdout 行前缀 `[ok]`/`[error]` 计数（L144-147）；stderr 最后 500 字符存 job.error。
- **约束**：模块级单例仅适用单进程部署（L37 注释）。迁 FastAPI 时等价于进程内全局状态 + `asyncio.create_subprocess_exec`。

### 空路由目录

`web/src/app/api/geocode/` 与 `web/src/app/api/pois/` 是**空目录**（无 route.ts）；`src/app/dashboard/`、`components/community/`、`components/dashboard/` 也是空目录。迁移时直接忽略。

---

## A2. 数据加载与评分

### data-loader.ts（`web/src/lib/data-loader.ts`）

- **L205-220 `getDataPaths()`**：11 个数据文件路径（见 data-inventory.md）。
- **加载时清洗逻辑（移植 FastAPI 必须带走）**：
  - L49-56 `cleanStationName`：地铁站名去 `A口/出入口/地铁站/(地铁站)` 后缀。
  - L59-65 医院清洗：`HOSPITAL_SKIP`（社康/诊所等跳过）、`HOSPITAL_SUFFIX`（科室/楼栋后缀剥离，最多 4 轮）、`HOSPITAL_ALIASES`（"邵逸夫医院"→正式名）。
  - L67 POI 展示围栏 `POI_BOUNDS = {latMin:30.12, latMax:30.26, lngMin:120.09, lngMax:120.29}`，全类型统一过滤（L114-116）。
  - L88-105 学校清洗：高校锚点截断（`校区/大学/研究院|学校|中学|小学|幼儿园|学院` 最后一次出现处截断），`SCHOOL_SKIP=/办事处/`。
  - L111-158 `deduplicatePOIs`：同名保留最近距离；subway/hospital/school 各有专属 key 策略。
  - L166-203 `mergePrefixNames`：全局前缀归并（"主体+后缀"并入已存在的"主体"），只作用于 hospital/school 两类。
  - L244-255 `loadCoordinates`：错区防护——`formatted_address` 不含"滨江区"的坐标剔除。
  - L356-399 `loadPriceSnapshots`：逐行解析 jsonl，同小区 `monthly_deal_avg_latest` 优先于 `visible_listing_unit_price_avg`。
- **L222-232 `loadJSON`**：文件不存在/解析失败返回 fallback（不抛错）。

### scoring.ts（`web/src/lib/scoring.ts`）

- **L8-21 `findNearestStation`**：等距近似（`M_PER_DEG_LAT=111320`，经度乘 cos(lat)），返回 `{name, distance(米)}`。
- **L24-29 默认权重**：`{location:30, amenity:30, product:25, market:15}`（价格不参与评分——types.ts L106 注释）。
- **四维公式**：
  - 区位 L37-41：≤400m → `100 - d*0.025`；否则 `max(20, 90 - (d-400)/30)`。null 当无地铁数据。
  - 配套 L47-93：类型权重 school .35 / hospital .20 / mall .20 / park .15 / bus .10；每类 `countScore = min(count*20, 60)`（3 个封顶）+ `distanceScore = max(0, 40 - nearest/30)`；缺类固定 10 分（`FACILITY_ABSENT_SCORE` L32）；学校按学段折算距离（小学/中学 ÷1.4、大学 ÷0.6，L73-81）。
  - 产品力 L104-134：楼龄 35%（当年 100，每年 -2.3，保底 30）/ 容积率 20%（≤1.0 →95-100，每 +1 扣 18，保底 30）/ 车位比 20%（`35 + r*50`，≥1.3 封顶 100）/ 物业费 15%（`45 + fee*15`，封顶 95）/ 绿化率 10%（`30 + rate*1.6`）；子项缺失自动剔除重归一化。
  - 市场面 L140-144：`dealCount<=0 → 30`；否则 `min(95, 35 + n*6.5)`。
  - 总分 L150-183：`round(Σ score*weight / Σ weight)`，clamp 0-100；全维度缺失 → 50。
- **L188-196 `calculateAllScores`**：批量包装。

### types.ts（`web/src/lib/types.ts`）

- 核心类型：`Community`（L2-22）、`PriceInfo`（L24-30）、`POI`/`POIType`（L48-56，6 类：subway/school/hospital/mall/park/bus）、`ScoreResult`（L98-104）、`ScoreWeights`（L108-113）、`SchoolLevel`（L68）。
- 关键纯函数（前后端共用，前端也直接 import）：
  - `getDisplayPrice`（L33-35）：`deal_avg_price ?? listing_avg_price`。
  - `getPriceColor`（L39-46）：五档色阶 <2万/#3D9147、<3.5万/#A8C03C、<5万/#E5B32C、<7万/#E2711D、≥7万/#D64545，无价 #9AA3AD。
  - `getSchoolLevel`（L90-96）：名称正则推断学段，null=培训机构噪音不绘制。
  - `SCHOOL_LEVEL_LABELS/COLORS`（L70-83）。
  - `POI_CONFIGS`（L121-128）：抓取半径/权重配置（采集脚本参考用）。
- `MOCK_COMMUNITIES`（L131-198）：3 条演示数据，仅 communities API 空数据兜底用。

### binjiang-boundary.ts（`web/src/lib/binjiang-boundary.ts`）

- L3-87：**硬编码 334 点**滨江区行政边界（GCJ-02，内联在 TS 源码里，不读 `data/binjiang_district_boundary.json`——该 json 只是溯源存档）。
- L90-101 `isInBinjiang`：射线法点在多边形内判断。
- **双端使用**：服务端（transit route 裁剪/过滤）+ 客户端（page.tsx L339 POI 围栏过滤）。迁移后此逻辑要同时存在于 FastAPI（transit 裁剪）和前端（POI 过滤），或改为 API 输出。

---

## A3. 高德依赖

### 服务端 REST 封装：`web/src/lib/gaode.ts`

- L4：`GAODE_API_KEY`（服务端 env，非 NEXT_PUBLIC）。
- 封装了 `geocode` / `reverseGeocode` / `searchPOI` / `calculateDistance` / `POI_TYPE_MAP`（高德类型码：subway 150500、school 150600、hospital 090100、mall 060101、park 110101、bus 150200）。
- **关键事实：当前没有任何 route.ts import gaode.ts**（api/geocode、api/pois 目录为空）。运行时 API 不调高德；高德 REST 仅在**采集脚本** `scripts/fetch_gaode_coordinates.py` / `fetch_gaode_pois.py` 中使用（key 来自 `scripts/_gaode_config.py`，已 gitignore）。

### 客户端 JS API：BinjiangMap.tsx

- L31：`NEXT_PUBLIC_GAODE_MAP_KEY`（加载 JS API 2.0，L141 `https://webapi.amap.com/maps?v=2.0&key=...&plugin=AMap.Scale,AMap.ToolBar`）。
- L134-138：`NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY` → `window._amapSecurityConfig.securityJsCode`。
- 三个 env 变量均定义在 `web/.env.local`（值已脱敏）：`GAODE_API_KEY`、`NEXT_PUBLIC_GAODE_MAP_KEY`、`NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY`。
- 迁移影响：地图渲染 key 必须进前端（NEXT_PUBLIC_ 前缀 + build-time inline）；REST key 归后端/采集脚本。

### refresh 是 Python 脚本驱动

`POST /api/refresh` spawn `python scripts/fetch_tmsf_price_snapshot.py`（见 A1.4），**不是纯前端逻辑**。迁移后此端点落在 FastAPI，spawn 目标改为后端仓库内的脚本。

---

## A4. 前端 fetch 调用点清单（迁移改 /api/map/* 用）

| # | 文件 | 行号 | 调用 | 迁移目标 |
|---|---|---|---|---|
| 1 | `web/src/app/page.tsx` | L12 | `fetch('/api/communities')`（fetchCommunities，L10-19） | `/api/map/communities` |
| 2 | `web/src/app/page.tsx` | L237 | `fetch('/api/transit')`（useEffect 内） | `/api/map/transit` |
| 3 | `web/src/app/page.tsx` | L289 | `fetch('/api/refresh', {method:'POST'})`（startRefresh） | `/api/map/refresh` |
| 4 | `web/src/app/page.tsx` | L302 | `fetch('/api/refresh', {method:'DELETE'})`（stopRefresh） | `/api/map/refresh` |
| 5 | `web/src/app/page.tsx` | L309 | `fetch('/api/refresh')`（3 秒轮询 GET） | `/api/map/refresh` |

- `BinjiangMap.tsx` **无任何 fetch**：communities/pois/transit 全部由 props 传入。
- `/api/score` 前端零调用（见 A1.2）。
- 共 5 处调用点，全部相对路径（无 basePath 前缀）。源项目 web 无 basePath（next.config.ts 为空配置），目标 apps/housing-map 将有 basePath=/map——相对路径 `/api/map/*` 与 basePath 无关（绝对路径），nginx 直转方案下不需要改写为 `/map/api/...`。

## Caveats / Not Found

- `docs/DATA_SOURCES.md` 与 transit 代码的线路处理描述不一致（文档说保留完整几何，代码做几何截断）；以代码为准。
- 源项目 `web/package.json`：next 16.2.6 / react 19.2.4 / tailwind v4（devDeps），与任务描述「Next.js 16.2.6」一致。`pnpm-workspace.yaml` 仅含 `ignoredBuiltDependencies: [sharp, unrs-resolver]`，不是多包 workspace。
- 源项目 web/AGENTS.md 提示 Next 16 有 breaking changes，需读 `node_modules/next/dist/docs/`（迁移实现时的注意事项）。
