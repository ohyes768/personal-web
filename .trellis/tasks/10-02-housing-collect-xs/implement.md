# Implement：采集扩展覆盖萧山接壤板块

> 顺序执行；每步末验证通过再进下一步。长耗时采集步骤先估配额/时长再跑。

## 步骤

1. **清单扩展** → 改 `fetch_tmsf_binjiang_communities.py` 过滤（in_collect_scope，design §1）
   → 重跑 → 验证：json 含双区小区，萧山候选 ~285（按研究口径），district/subdistrict 完整
2. **坐标补抓** → 改 `fetch_gaode_coordinates.py` 地址按 district 构造 → 只抓无坐标小区
   → 验证：新增小区坐标缺失率 <5%；落点统计（is_in_scope 命中数 vs 候选数）
3. **属性补抓** → `fetch_tmsf_property_type` / `product_attrs` / `community_age`
   对新增 id 跑 → merge → 验证：新小区三文件覆盖率（property_type ≥90%）
4. **POI 重采** → `fetch_gaode_pois.py` 围栏改 is_in_scope；先打印分片/配额预估
   → 跑 → merge → 验证：萧山板块小区 amenity 评分非空
5. **轮廓链路** → fetch_osm_polygons（bbox 已扩）→ convert → extract（is_in_scope）→ build_merged
   → 验证：萧山板块小区有轮廓的比例不低于滨江（OSM 数据密度差异可接受则记录）
6. **坐标校准** → fix_mislocated / fix_road_named 跑一遍 → 验证：围栏外小区清零或入排除名单
7. **全量刷新实测** → 手动 POST /api/refresh → 记录时长；>15min 则 REFRESH_CRON 双周化
   → 验证：价格快照含新增小区；无批量 403
8. **market_reference** → scope 扩展双区（口径实现时看 fetch 脚本）
9. **收尾** → pytest 全绿 → spec 更新（采集范围一节）→ commit → 归档

## 回滚点

- 每个数据文件重采前备份（沿 refresh.py 惯例 .bak）
- 清单/坐标/属性均可由旧 json + 脚本重跑恢复；无 schema 迁移

## 验证命令

```bash
cd backend/housing-map && uv run pytest tests/ -q
```
