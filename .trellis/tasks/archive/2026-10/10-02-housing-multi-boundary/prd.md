# PRD：围栏多边形化 — boundary 支持多围栏并接入萧山板块边界

> Parent: [10-02-housing-expand-xs-border](../10-02-housing-expand-xs-border/prd.md) · 子任务 1/3 · 先行

## 需求

`src/core/boundary.py` 从"单一滨江 334 点多边形"升级为"多边形集合"，并新增萧山接壤板块围栏，供 transit 裁剪、站点过滤与后续采集/前端复用。

### 改动点

1. **boundary.py 重构**：
   - `BINJIANG_BOUNDARY` 保留（点集不动，与源项目逐点一致的历史约束解除前不改）
   - 新增 `XIAOSHAN_BORDER_BOUNDARY`（萧山接壤板块围栏，从高德行政区 API 拉板块级边界合并，或按街道 polygon 合并；GCJ-02，与现有一致）
   - 新 API：`is_in_scope(lon, lat) -> bool`（点在任一围栏内）与 `SCOPE_BOUNDARIES: list[list[list[float]]]` 导出；旧 `is_in_binjiang` 保留为滨江单区语义（前端区筛选用得上）
2. **transit.py 跟随**：地铁线路几何裁剪与站点过滤从 `is_in_binjiang` 切到 `is_in_scope`（15 处引用逐一核对语义，站点过滤应为"围栏集合内"）。
3. **萧山板块地铁数据**：现 `binjiang_transit_routes/stops.geojson` 按滨江围栏裁剪，萧山板块内的线路段/站点（如 6/7 号线世纪城段、闻堰方向线路）需按新围栏重采（fetch_osm_layers + convert_osm_transit 重跑），产出合并到现有文件。
4. **测试重写**：`test_boundary.py` 的 334 点断言保留；新增多围栏用例（滨江点/萧山板块点内、萧山非板块点如临浦外、杭州主城点外）；`test_transit.py` 裁剪用例按双围栏更新。

### 关键设计约束

- 围栏坐标系统一 GCJ-02（高德），与现有数据一致
- 萧山板块围栏来源优先级：高德行政区 API（街道级 polygon）> OSM 手动圈选。**不自己画多边形**（边界歪了会裁掉真实小区）

## 验收标准

1. `is_in_scope` 覆盖滨江 + 确认清单内的萧山板块；板块清单外萧山区域返回 False。
2. `python -m pytest tests/ -v` 全绿（围栏/裁剪测试按新结构等价覆盖后）。
3. `/api/map/transit` 返回的线路/站点含萧山板块内段，且滨江段与改造前一致（零回归，可用改造前响应 diff 验证）。

## 不做

- 前端围栏（binjiang-boundary.ts）—— 子任务 3
- POI/小区采集范围 —— 子任务 2（本任务只提供围栏几何）
