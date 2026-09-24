# Housing-Map 小区准入契约

> **适用场景**：改小区可见性 / 刷新采集范围 / 轮廓生成，或排查"某小区数据没抓下来/地图看不到"。

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
