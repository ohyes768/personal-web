# 房天下采集契约（已退役，2026-11-03）

房天下采集能力已退役：CLI `scripts/fetch_fang_rentals.py`、实现 `src/services/fang_rentals.py`、
请求策略 `src/services/fang_request_policy.py`、详情缓存 `src/services/fang_detail_cache.py`
与说明 `scripts/FANG_RENTALS.md` 全部删除，本文件只保留退役事实，不再是执行契约。

- 唯一当前租金来源是幸福里；社区台账（`community_registry.sqlite3`）是关联权威。
- 旧房天下映射文件（`data/rental_community_mappings.json`）与旧映射库不再被读取或重新导入，
  也不再作为容器种子分发；历史数据、人工决定与快照保留在原处，只读。
- 旧来源写入口（`POST/PUT .../rental-source`、`DELETE .../rental-source/candidates/{id}`）
  返回 410 且无副作用；不得恢复房天下采集、映射或候选池。
- 历史房天下关联不参与当前来源选择、租金统计与自动用途判定；前端只读显示「房天下（历史）」。
- 当前实现契约见 [housing-map-rental-reference.md](./housing-map-rental-reference.md) 与
  [xingfuli-rentals.md](../backend/housing-map/backend/xingfuli-rentals.md)。
