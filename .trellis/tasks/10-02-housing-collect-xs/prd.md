# PRD：采集扩展 — 小区清单/POI/坐标/轮廓覆盖萧山接壤板块

> Parent: [10-02-housing-expand-xs-border](../10-02-housing-expand-xs-border/prd.md) · 子任务 2/3 · 依赖围栏多边形化（子任务 1）

## 需求

采集管线从滨江区扩展到"滨江 + 萧山接壤板块（以 parent PRD 确认清单为准）"，产出合并进现有数据文件（不拆分双套文件）。

### 前置研究（implement 前必须完成）

用透明售房网全杭小区清单实测候选板块小区量级（`subdistrict` 分组计数），产出写到本任务 research/ 目录，并据实敲定板块清单。**若三板块合计 > 300，回到 parent 决策**。

### 改动点

1. **小区清单**：`fetch_tmsf_binjiang_communities.py` 的 `BINJIANG_PREFIX = "滨江"` 过滤扩展为：`district == 滨江` 或 `district == 萧山 and subdistrict ∈ 板块清单`。重跑产出合并进 `binjiang_communities.json`（保留原文件名）。
2. **房产属性**：`fetch_tmsf_property_type / product_attrs / community_age` 对新增小区补抓，合并对应 json。
3. **坐标**：`fetch_gaode_coordinates.py` 对新增小区补抓（高德 POI 搜索，注意配额）。
4. **POI 配套**：`fetch_gaode_pois.py` 按新围栏（子任务 1 的 `SCOPE_BOUNDARIES`）重抓萧山板块教育/医疗/商业 POI，合并 `binjiang_pois.json`。
5. **住宅轮廓**：`fetch_osm_polygons / convert_osm_residential / extract_binjiang_polygons / build_merged_polygons` 链路对萧山板块重跑合并。
6. **坐标校准**：`fix_mislocated_communities` / `fix_road_named_communities` 对新数据跑一遍，排除错位/道路伪小区。
7. **价格快照**：现有手动/定时刷新走 `select_refresh_targets`（`is_real_community` 全量口径），新小区入库后自动纳入，无需改代码；但**刷新时长重估**（见下）。
8. **定时刷新重估**（2026-09-30 加的 scheduler）：小区数增加后全量时长变化，若 >15 分钟则降频（每周 → 双周）或在 PRD 评审时定增量方案。cron 时间的调整在实现时按实测定。
9. **market_reference.json**：市场行情快照 scope 扩展双区（看板展示用），口径与实现时确认。

### 数据安全

- 所有重采前备份原 jsonl/json（沿 refresh.py 的备份惯例）
- 新旧合并策略：新记录优先、无新记录保留旧（与 `merge_snapshot_rows` 一致）
- 高德 key 配额：POI/坐标补抓估算调用量，超配额风险先报告再执行

## 验收标准

1. `binjiang_communities.json` 含双区小区，`district/subdistrict` 字段完整可区分；量级在预期范围。
2. 新增小区坐标齐全（坐标缺失率 < 5%）、物业类型/房龄覆盖。
3. POI 数据覆盖萧山板块（板块内小区评分的 amenity 维度非空）。
4. 手动触发一次全量刷新成功，时长实测记录，价格快照含新增小区。
5. `python -m pytest tests/ -v` 全绿；无批量 403/超时（反爬风险未恶化）。

## 不做

- 萧山非板块小区
- 评分算法调整
- 前端展示（子任务 3）
