# 萧山三街道围栏来源研究（2026-10-02）

## 结论：Nominatim（OSM）+ WGS-84→GCJ-02 转换

| 来源 | 街道级结果 |
|------|-----------|
| 高德 v3 district API（extensions=all） | ❌ 街道级（level=street）不返回 polyline，仅区县以上 |
| DataV GeoAtlas areas_v3 | ❌ 单街道 12 位/9 位代码文件均 404，区级 `_full` 404 |
| Overpass admin_level=10 | ❌ 0 结果（中国街道级 OSM 覆盖不全） |
| Overpass admin_level=8 | ❌ 504 网关超时（重试仍超时） |
| **Nominatim polygon_geojson=1** | ✅ 闻堰/宁围/盈丰 三个街道均返回 Polygon（WGS-84） |

盈丰街道（2021 年新设）在 Nominatim 有边界，无需 fallback 到手动圈选。

## 采获的街道代码（统计用区划代码，备用）

- 闻堰街道 330109012000、宁围街道 330109013000、盈丰街道 330109015000

## 实施要点

- Nominatim 返回 WGS-84；项目围栏/坐标体系为 GCJ-02（高德）。
  转换复用 `scripts/convert_osm_transit.py` 的 `wgs84_to_gcj02`。
- Nominatim 用法约定：自定义 UA、串行请求间隔 ≥ 1s（本次已遵守）。
- 高德 key 无法用于街道边界，`_gaode_config.py` 不参与本链路。
