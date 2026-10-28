# 现状核对：线上缺口、快照覆盖、既有代码事实

核对时间：2026-10-28。全部只读操作，未修改任何线上或本地数据。

## 1. 线上缺口（只读访问 https://web.duomi77.cn:9443/api/map/communities）

`stats` = `{admitted: 160, displayed: 135, hidden: {missing_boundary: 25}}`，`data` 共 160 条。

25 个"无可展示轮廓"的小区（boundary 字段缺失 / boundary_source 缺失，全部 property_type=住宅）：

| community_id | 名称 | 经度 | 纬度 |
|---|---|---|---|
| 10000486 | 迎春小区 | 120.221355 | 30.196095 |
| 10001734 | 钱江彩虹城 | 120.155797 | 30.189790 |
| 10005183 | 银爵世纪公寓 | 120.146963 | 30.170180 |
| 1024 | 朗庭 | 120.198129 | 30.172806 |
| 167483594 | 兴耀鑫都汇 | 120.218675 | 30.182775 |
| 1836435617 | 保利天汇 | 120.198146 | 30.182901 |
| 20000561 | 钱塘大观 | 120.133258 | 30.181901 |
| 20000608 | 现代印象广场 | 120.171142 | 30.185097 |
| 20043161 | 绿地旭辉城 | 120.229217 | 30.224480 |
| 20096840 | 长虹苑 | 120.176922 | 30.174123 |
| 5000203 | 滨康二苑 | 120.209180 | 30.177841 |
| 5000775 | 湖漫雅筑 | 120.198129 | 30.170314 |
| 5001332 | 龙湖春江郦城 | 120.204728 | 30.198884 |
| 5001511 | 歌山品悦府 | 120.224917 | 30.190687 |
| 5001569 | 钱江水晶澜轩 | 120.166443 | 30.191724 |
| local-11c4ff600c4452b9 | 中海万潮玖序 | 120.211325 | 30.214436 |
| local-234d195ab0ed56d5 | 世茂栖棠誉湾 | 120.146374 | 30.165397 |
| local-2681e8fed6025fc4 | 潮起江南城 | 120.227291 | 30.213580 |
| local-28c006e18e155c5a | 春来晴翠园 | 120.156831 | 30.149919 |
| local-2a61306dc4505469 | 水晶城水晶澜轩 | 120.166443 | 30.191724 |
| local-300f814be4f554d5 | 彩虹城 | 120.155797 | 30.189790 |
| local-3165aab612e15266 | 滨江兴耀锦川源府 | 120.223073 | 30.185633 |
| local-a9354a29596c537f | 望天际公寓 | 120.220351 | 30.219937 |
| local-dca97029830a53d8 | 泊玺骏庐 | 120.188230 | 30.151844 |
| local-f94bf7974fa9524e | 雯月隽庐 | 120.149851 | 30.167614 |

注意：钱江彩虹城/彩虹城、钱江水晶澜轩/水晶城水晶澜轩 坐标完全相同（同一实体的重复收录条目）。

## 2. 缺口判定口径（必须复用，不能另起一套）

`backend/housing-map/src/api/routes.py` `get_communities()` 已在算 `missing_boundary`：

```python
for view in admitted_views:
    if view['map_status'] == 'displayed':
        polygon = polygons.get(view['community_id']) or {}
        if not polygon.get('rings') or polygon.get('source') == 'shp':
            hidden['missing_boundary'] += 1
```

即"无可展示轮廓" = 基础条目无 rings **或** source=='shp'。`src/services/community_admission.py::map_status` 本身不返回 missing_boundary。

推论：新流程的有效轮廓视图与缺口判定必须与上面这段完全一致：
- 有 rings 且 source != 'shp' → 已展示
- 无条目 / 无 rings / source=='shp' → 缺口
- 新增人工覆盖层（overrides）后，覆盖层 rings 视为有效轮廓（source='osm-building'），缺口消失。

## 3. 部署版本与仓库 master 的关系（重要）

首次访问线上时返回了仓库里根本不存在的 `missing_boundary` 状态。原因是**本地 master 落后远端 7 个提交**，
`git fetch` 后发现远端已包含：

- `0837d0d` 问号占位不计入展示数量 → 引入 missing_boundary 统计
- `afc39c1` 按有效已收录住宅生成边界 → `build_merged_polygons.py` 改用 `community_views`
- `80d7c92` 保留已验证定位地址避免地图误过滤
- `9145a90` 区分高德地址建议与不完整地点结果

已 `git merge --ff-only origin/master` 同步，本任务全部实现基于 `80d7c92`。

## 4. OSM 快照现状

- 快照文件（`data/binjiang_osm_*_raw.json`）**在 .gitignore 中**（"Regenerable script captures"），
  不进 git；Dockerfile `COPY data ./data` 会带上构建机目录里的文件，但 NAS 部署是 `git pull` 后本地构建，
  NAS checkout 上大概率没有这些快照 → **生产环境大概率只能走在线 Overpass**。
- 本地存在的快照：
  - `binjiang_osm_buildings_all_raw.json` 9.6MB（2026-10-17，全量 building + residential 面，覆盖 BINJIANG_BBOX 30.10–30.26/120.10–120.28）
  - `binjiang_osm_named_buildings_raw.json` 2.3MB（2026-10-02）
  - `binjiang_osm_residential_raw.json` 1.9MB（2026-10-02）
- 结论：新流程必须把"快照缺失/不覆盖"当正常路径，落到在线补查；不能把滨江快照当成萧山已覆盖的证明。

## 5. 离线试算结果（用本地全量快照，对 25 个缺口小区）

`scripts/estimate_boundaries.py` 的 `load_snapshot` + `select_buildings` + `build_boundary` 直接跑：

- 可生成（非低置信）16 个
- 低置信 6 个：兴耀鑫都汇(1 面 0.05ha)、中海万潮玖序(1 面 0.21ha)、潮起江南城(1 面 2.05ha)、
  滨江兴耀锦川源府(20 面 1.4ha)、望天际公寓(6 面 1.22ha)、雯月隽庐(1 面 0.08ha)
- 无建筑失败 3 个：朗庭、春来晴翠园、泊玺骏庐（需在线 Overpass 补查）

面积参考：多数在 0.1–17 公顷之间。"1 面"的小区说明 OSM 侧只有住宅面（landuse=residential）没有 building，
按 PRD 要求不能一律叫"楼栋数"。

## 6. 既有代码事实（实现时必须对齐）

| 事实 | 位置 | 影响 |
|---|---|---|
| `load_polygons()` 兼容顶层 dict 与 `{"polygons": {...}}` 包装 | `src/services/data_loader.py:316` | 脚本里直接读 JSON 会把 "polygons" 当成小区 ID，缺口判定必须走 `load_polygons()` |
| `merge_boundaries` 只有进程内 `threading.Lock`，`meta.update` 可覆盖结构字段 | `src/services/boundary_import.py:33` | 新流程不接受浏览器直接提交 rings/meta |
| 旧导入接口要求 `HOUSING_ADMIN_TOKEN`，未配置时整体 503 | `src/api/boundary_import_routes.py:33` | 新流程走独立公开路由，不依赖旧 token |
| 旧导入的环校验只查"≥4 点且首尾闭合"，无有限值/有效性/面积下限 | `src/api/boundary_import_routes.py:54` | 新流程在生成与应用两端都要补严格几何校验 |
| `build_merged_polygons.main` 整体重写 `binjiang_polygons_merged.json` | `scripts/build_merged_polygons.py` | 人工确认结果必须独立存 overrides，查询时叠加，不能靠写基础文件 |
| `community_registry.db()` 用 `BEGIN IMMEDIATE` + `timeout=15` | `src/services/community_registry.py:53` | 工作流 SQLite 沿用同样的连接/事务习惯 |
| `boundary_refresh` 用 `asyncio.to_thread` 跑重建 | `src/services/boundary_refresh.py` | 新流程的后台生成同样需要线程执行器 |
| Docker 只跑单个 uvicorn worker | `docker-compose.nas.yml` | 单执行器 + 持久任务即可，不引入 Redis/Celery |

## 7. 仍需确认的事

- NAS 数据卷上是否实际存在 OSM 快照（决定生产默认走快照还是在线）。无法从本机只读确认；
  实现上按"快照优先、不覆盖则在线"处理，两条路径都测。
- 生产是否已有 `source == 'shp'` 的条目：当前线上 25 个缺口全部是"无条目"（boundary_source 为 None），
  没有 shp。shp 分支按代码路径覆盖，测试用 fixture 构造。
