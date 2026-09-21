# Research: 数据文件与采集脚本盘点（hangzhou-housingmap）

- **Query**: 滨江购房地图迁移 — 调研项 A5-A6（data/ 引用盘点 + 最小迁移清单 / scripts/ 依赖）
- **Scope**: internal（F:/personal-projects/hangzhou-housingmap）
- **Date**: 2026-09-18

## A5. data/ 目录盘点（git 追踪 35 个文件，工作区另有 gitignore 忽略的 3 类）

### 运行时被引用的文件（data-loader.ts L205-220 + transit/refresh route 直读）—— 11 个

| 文件 | 大小 | 引用处 | 用途 |
|---|---|---|---|
| `binjiang_communities.json` | 209 KB | data-loader L208 | 小区名录（421 个，含 community_id/name/district/subdistrict/address） |
| `binjiang_coordinates.json` | 65 KB | data-loader L209 | 小区坐标 `{id: {latitude, longitude, formatted_address}}`（GCJ-02） |
| `binjiang_pois.json` | 7.9 MB | data-loader L210 | 每小区周边 POI `{id: {pois: {type: POI[]}}}`（6 类设施） |
| `price_snapshots.jsonl` | 402 KB | data-loader L211 + refresh route 读写 | 价格快照（每行一条：community_id/avg_price/price_type/listing_count/deal_count/snapshot_date...） |
| `property_types.json` | 92 KB | data-loader L212 | 物业类型 `{id: {property_type}}`（住宅/写字楼/公寓/商贸/其他） |
| `binjiang_polygons_merged.json` | 198 KB | data-loader L213 | 小区边界轮廓 `{polygons: {id: {source: shp/osm, rings}}}`（GCJ-02） |
| `binjiang_subway_stations.json` | 2.8 KB | data-loader L214 | 地铁站坐标 `[{name, longitude, latitude}]`（评分用最近站） |
| `community_ages.json` | 44 KB | data-loader L215 | 建成年代 `{id: {name, build_year}}` |
| `community_attrs.json` | 71 KB | data-loader L216 | 产品力属性 `{id: {parking_spots, households, property_fee, gross_area_sqm, far_ratio, greening_rate}}` |
| `binjiang_transit_routes.geojson` | 1.85 MB | data-loader L217 + transit route L114 直读 | 地铁线路 FeatureCollection（GCJ-02 LineString） |
| `binjiang_transit_stops.geojson` | 426 KB | data-loader L218 + transit route L117 直读 | 轨道站点 FeatureCollection（GCJ-02 Point） |

**refresh 流程运行时生成（非源数据，但会出现在 data/）**：`price_snapshots.csv`（人工查看副本）、`price_snapshots_<date>.bak.jsonl`（自动备份）。

### 不被运行时引用的文件（24 个 git 追踪 + 3 类 gitignore）

| 文件/目录 | 大小 | 性质 |
|---|---|---|
| `_temp_extract/Hangzhou_202302.{shp,dbf,prj,shx}` | 4 件 | Shapefile 中间产物；`build_merged_polygons.py` L25 的兜底输入（SHP 来源轮廓，前端当前不展示 boundary_source=shp，见 BinjiangMap.tsx L247-248） |
| `binjiang_communities.csv` | 85 KB | fetch_tmsf_binjiang_communities 的 CSV 副本（人读） |
| `binjiang_communities.json.bak` | 221 KB | 旧备份 |
| `binjiang_communities_formatted.json` | 73 KB | 旧格式化版本 |
| `binjiang_communities_with_property_type.{csv,json}` | 88+235 KB | 旧中间产物（property_types.json 的前身） |
| `binjiang_coordinates.json.bak` | 69 KB | 旧备份 |
| `binjiang_district_boundary.json` | 8.3 KB | 滨江区边界溯源存档；**运行时不用**（334 点已硬编码进 `web/src/lib/binjiang-boundary.ts` L3-87） |
| `binjiang_osm_green_raw.json` | 1.7 MB | Overpass raw（绿地图层，当前无转换脚本消费） |
| `binjiang_osm_named_buildings_raw.json` | 636 KB | Overpass raw；`convert_osm_residential.py` L6 输入 |
| `binjiang_osm_pois_raw.json` | 310 KB | Overpass raw（未被消费） |
| `binjiang_osm_residential.geojson` | 745 KB | convert_osm_residential 输出 → `build_merged_polygons.py` L26 输入 |
| `binjiang_osm_residential_raw.json` | 370 KB | Overpass raw；convert 输入 |
| `binjiang_osm_residential_rel_raw.json` | 4.8 KB | Overpass raw（relation，未消费） |
| `binjiang_osm_roads_raw.json` | 5.0 MB | Overpass raw（道路，未消费） |
| `binjiang_osm_transit_routes_raw.json` | 2.9 MB | Overpass raw；`convert_osm_transit.py` 输入 |
| `binjiang_osm_transit_stops_raw.json` | 379 KB | Overpass raw；convert_osm_transit 输入 |
| `binjiang_osm_water_raw.json` | 1.1 MB | Overpass raw（水系，未消费） |
| `price_snapshots_2026-05-11.bak.{csv,jsonl}` | 224+273 KB | 过期备份（DATA_SOURCES.md 注明不再使用） |
| `price_snapshots_2026-09-16.bak.jsonl` | 435 KB | refresh 自动备份 |
| ~~`杭州.rar` / `index_search_*.js` / `debug_*.html`~~ | — | **已被根 .gitignore 忽略**（`*.rar`、`data/index_search_*.js`、`data/debug_*.html`），git 里没有 |

### 必须迁移的数据文件最小清单

**方案一（仅运行时，11 个，约 10.6 MB）**：上表"运行时被引用"的 11 个文件。

**方案二（运行时 + 可再生成轮廓/线路，追加 9 个，约 +12 MB）**：另迁 `_temp_extract/` 4 件 shp、`binjiang_osm_residential.geojson`、`binjiang_osm_residential_raw.json`、`binjiang_osm_named_buildings_raw.json`、`binjiang_osm_transit_routes_raw.json`、`binjiang_osm_transit_stops_raw.json`——否则 `build_merged_polygons.py` / `convert_osm_transit.py` 无法重跑，轮廓与地铁数据变成一次性快照。

价格类数据（price_snapshots.jsonl）是 refresh 流程唯一会写的数据，其余 10 个为只读静态数据。

## A6. 采集脚本依赖（scripts/，16 个 git 追踪文件）

### 脚本清单与角色

| 脚本 | 角色 | 依赖 |
|---|---|---|
| `fetch_tmsf_price_snapshot.py` | **refresh 流程唯一直接调用**（spawn）；抓透明售房网价格快照 | 纯标准库（urllib/csv/json/re/statistics/subprocess...） |
| `fetch_tmsf_binjiang_communities.py` | 小区名录采集 | 标准库 + `from fetch_tmsf_price_snapshot import (…)`（复用抓取函数） |
| `fetch_tmsf_community_age.py` | 建成年代 → community_ages.json | 标准库 + import price_snapshot 的 `BASE_URL, fetch_html_with_curl, input_value_by_id, strip_tags` |
| `fetch_tmsf_product_attrs.py` | 产品力属性 → community_attrs.json | 标准库 + 同上 import |
| `fetch_tmsf_property_type.py` | 物业类型 → property_types.json | 标准库 + 同上 import |
| `fetch_gaode_coordinates.py` | 高德地理编码 → binjiang_coordinates.json | 标准库 + `import _gaode_config`（GAODE_API_KEY） |
| `fetch_gaode_pois.py` | 高德周边搜索 → binjiang_pois.json | 标准库 + `_gaode_config` |
| `fetch_osm_layers.py` | Overpass 按图层下载 raw | 标准库 |
| `convert_osm_residential.py` | raw → residential.geojson（WGS84→GCJ-02） | 标准库 |
| `convert_osm_transit.py` | raw → transit_routes/stops.geojson（WGS84→GCJ-02） | 标准库 |
| `build_merged_polygons.py` | OSM+SHP 合并 → binjiang_polygons_merged.json | 标准库（含 struct 读 shp） |
| `extract_binjiang_polygons.py` | 从 shp 提取轮廓（早期脚本） | 标准库 |
| `fetch_osm_polygons.py` | OSM 建筑轮廓（早期脚本） | 标准库 |
| `fix_mislocated_communities.py` | 修错位小区坐标 | 标准库 |
| `fix_road_named_communities.py` | 修路名伪小区 | 标准库 |
| `fetch_property_type_cdp.js` | Node/CDP 抓物业类型（早期，被 py 版替代） | Node + chrome-remote-interface（无 package.json，手工环境） |

### 依赖结论

- **无 requirements.txt / pyproject.toml**：所有 Python 脚本**纯标准库**（grep 全部 import 验证，第三方仅 `concurrent.futures` 等内置模块）。迁移到 backend/housing-map 不引入任何 pip 依赖。
- **跨脚本 import**：4 个脚本 import `fetch_tmsf_price_snapshot` 的共享函数（BASE_URL/fetch_html/strip_tags 等）——脚本必须整体迁移，不能只搬 refresh 用到的一个。
- **API key 配置**：`scripts/_gaode_config.py`（内容仅 `GAODE_API_KEY = "..."`，**已被 .gitignore 忽略，不在 git 里**）。仅 fetch_gaode_coordinates.py / fetch_gaode_pois.py 两个脚本需要它。tmsf 系脚本不需要 key（公开页面抓取 + UA 伪装）。
- **运行环境**：Python 3.14（`__pycache__` 中 .cpython-314.pyc）；refresh route spawn 的是 `python`（裸命令，依赖 PATH）。

## Caveats / Not Found

- `data/binjiang_district_boundary.json` 虽不被运行时引用，但它是 `binjiang-boundary.ts` 334 点硬编码的来源（高德行政区 API 2026-09-15 拉取）。若希望 FastAPI 版从数据文件加载边界而非硬编码，可迁移此文件；否则纯存档。
- refresh 的备份文件会持续累积在 data/（每次 POST 生成一个 `<date>.bak.jsonl`），NAS volume 部署时无自动清理。
- `fetch_property_type_cdp.js` 需要 Node 环境 + 浏览器，是早期一次性工具，可评估不迁移。
