# Housing-Map 小区准入契约

> **适用场景**：改小区可见性 / 刷新采集范围 / 轮廓生成 / 覆盖范围围栏，或排查"某小区数据没抓下来/地图看不到"。

## 契约

准入分两层，**采集与展示全量，只有轮廓按住宅口径**：

| 函数 | 规则 | 调用方 |
|------|------|--------|
| `is_real_community`（community_filters.py） | 仅排除道路名后缀（大道/路/街/巷）、`EXCLUDED_COMMUNITY_NAMES`、空名；**不看物业类型** | `/api/map/communities`（routes.py）、刷新目标集（refresh.py `select_refresh_targets`） |
| `is_residential_community` | `is_real_community` + 物业类型 ∈ {住宅, 别墅, 排屋} | `build_merged_polygons.py`（OSM residential 数据源限制，非住宅无轮廓，前端以占位多边形+问号点位渲染） |

前端默认筛选 = `{住宅, 别墅, 排屋}`（page.tsx propertyTypes 初始值），商办类（写字楼/公寓/商贸/其他）需手动勾选或选"全部"。**默认视野等价于旧后端白名单口径**。

## 为什么是"全量采集"（2026-09-24 决策）

旧版把 `is_residential_community` 同时用在展示+采集+轮廓三处，导致透明售房网物业类型标"其他"的小区（如逸天广场 10004960）整体消失：地图搜不到、刷新永不采集、旧快照停更。用户决策：界面已有物业类型筛选，采集下发全量、展示差异交给前端，默认只显住宅类。

## 排查"某小区看不到"的路径

1. `property_types.json` 里该小区的 `property_type` 是否为 null → 现在也会下发（仅在"全部"里可见）
2. 名称是否以道路后缀结尾 / 在排除名单
3. 是否在 `MERGE_DROP_IDS`（合并组 drop 成员）
4. 前端当前勾选的类型 chips

## 定时刷新（2026-09-30 新增，2026-10-02 双周化）

`src/scheduler.py`（精简自 macro 的 src/scheduler/，无 API 管理/执行历史）：

- **cron** `17 21 * * mon`（每周一 21:17 Asia/Shanghai）触发，**job 内 ISO 周奇偶节流双周执行**（扩萧山后 581 小区实测 29 分钟 > 15 分钟阈值；cron 保持每周触发以保留 misfire 补偿）。任务体调 `refresh.start_refresh(0)` 全量。
- **互斥**：与前端手动刷新共用 `refresh.py` 的 `job["running"]`；定时触发撞上运行中任务返回 409，scheduler 侧记 warning 跳过，不排队。
- **陷阱**（继承 macro）：APScheduler 3.x dow 数字 0=周一（非 crontab 的周日），星期一律写英文缩写；`from_crontab` 必须显式传 `timezone="Asia/Shanghai"`，否则容器内按 UTC 触发偏移 8 小时。
- 手动刷新 API（`POST /api/refresh`）与前端交互不变。

## 采集范围（2026-10-02 扩萧山接壤板块）

**tmsf 板块口径 ≠ 行政街道**：行政「盈丰」街道在 tmsf 记作「钱江世纪城」，「开发区」部分落宁围街道，「湘湖」实测 100% 围栏外不取。板块清单（`fetch_tmsf_binjiang_communities.py` 的 `XIAOSHAN_PLATES`）= {钱江世纪城, 开发区, 宁围, 闻堰}，映射实测见 task 10-02-housing-collect-xs research/。

**多层口径一致性**（同一小区集合流过全链路，改围栏/板块清单时四处同步）：

| 层 | 位置 | 口径 |
|----|------|------|
| 展示 | routes.py `/communities` | `is_real_community` + 坐标 `is_in_scope`（围栏外不下发） |
| 刷新目标 | refresh.py `select_refresh_targets` | 同上（省时长） |
| 坐标装载 | data_loader.py `load_coordinates` | 地址含滨江区 ∪ (萧山区 且 萧山板块围栏内)——防跨区错配 |
| POI 展示 | data_loader.py `POI_BOUNDS` | scope 围栏外接框（动态算，勿硬编码） |

- `nearest_subway` 用 `/api/transit` 同源动态站点（`_station_list_for_scoring`），不再用旧静态 `binjiang_subway_stations.json`（该文件已无引用，保留仅为回滚）。
- 地理编码对萧山小区失准率高（~20% 解析到城区中心）：`fix_mislocated_communities.py` 出界判定用 `is_in_scope` 多边形（bbox 会漏框内多边形外的失准点），重定位后 POI 自动清空待重抓。
- **顺序依赖**：`fix_road_named_communities.py` 按价格记录判存废——新增小区必须先跑全量刷新再跑它，否则无价格的新小区会被误删。
- `market_reference.json` 是人工校验的挂牌参考行情（安居客快照），scope 仍为滨江区，萧山部分待人工补录。

## 覆盖范围围栏（2026-10-02 扩展）

`src/core/boundary.py` 从单围栏改为多围栏集合，覆盖滨江 + 萧山接壤三街道（盈丰/宁围/闻堰）：

| 函数 | 语义 | 调用方 |
|------|------|--------|
| `is_in_binjiang` | 滨江单区（`BINJIANG_BOUNDARY` 334 点不动） | 前端区筛选、区判定的既有语义 |
| `is_in_xiaoshan_border` | 萧山三板块任一（`XIAOSHAN_BORDER_BOUNDARIES`，键为街道名） | — |
| `is_in_scope` | 滨江 ∪ 萧山板块 | transit 线路裁剪/站点过滤（`clip_to_scope`）等一切"覆盖范围"判断 |

- **数据来源**：Nominatim `polygon_geojson=1`（WGS-84）→ `convert_osm_transit.wgs84_to_gcj02` → Douglas-Peucker 抽稀（ε=1e-4 度）→ 首尾闭合。脚本 `scripts/fetch_street_boundaries.py`。高德 district API 街道级无 polyline、DataV 街道文件 404、Overpass admin_level=10 无结果——勿重复探测。
- **点数契约**：`/api/map/transit` `meta.boundary_points` = 全部围栏点数之和（334+200+100+34=668），test_api.py 有硬断言；改围栏需同步。
- **OSM 采集 bbox**：`scripts/fetch_osm_layers.py` 的 `BBOX` 已北/东扩到宁围北界；地铁 raw→geojson 后须重跑对比（滨江段逐点零回归 + 板块新站出现），基线对比脚本见本任务 research/。
- **板块间贴缝**：三街道多边形各自独立抽稀，接缝处不共边——`seg_boundary_intersect` 二分定位到哪条边界取决于路径，属预期几何行为，测试已按"顶点并集"断言。
