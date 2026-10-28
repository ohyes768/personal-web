# design — estimate_boundaries.py

## 形态

单文件脚本 `backend/housing-map/scripts/estimate_boundaries.py`(跟随 build_merged_polygons.py 惯例),标准库 + shapely(需加入 backend/housing-map 依赖)+ urllib。子命令:

```
python scripts/estimate_boundaries.py                 # 估算全部目标,输出候选+预览
python scripts/estimate_boundaries.py --ids 20000608  # 指定小区
python scripts/estimate_boundaries.py --apply --selection estimate_out/selected.json [--api http://host:8096]
```

## 数据与目录

- 名单派生:registry(经 community_views)取展示小区;无轮廓 = polygons 文件(`binjiang_polygons_merged.json`,结构 `{_meta, <cid>: {rings, source}}`)无该 cid;坐标取 registry `longitude/latitude`(GCJ02)。
- `estimate_out/`(输出,gitignore):`candidates.geojson`、`estimate_preview.html`、`selected.json`、`cache/<cid>.json`(Overpass 原始响应,TTL 7 天)。

## Overpass 客户端

- 镜像序列:`overpass-api.de` → `overpass.kumi.systems` → `overpass.private.coffee`;单个失败(含 406/429/5xx/超时 60s)换下一个,全挂则该小区记失败继续下一个。
- 请求间隔 10s(`time.sleep`);缓存命中(7 天内)不发请求。
- 查询:`way["building"](bbox)` + `way["landuse"="residential"](bbox)` + 具名 way(name 存在),bbox = 定位点 ±0.002°;UA 带项目标识。
- 定位点为 GCJ02,查 Overpass 需先转 WGS84(与落盘方向相反的转换,同一对函数互逆)。

## 挑楼聚类(核心算法)

1. 名称优先:way 的 name 含小区主名/别名 → 直接入选。
2. 距离过滤:楼面质心距定位点 >250m 丢弃。
3. 连通聚簇:shapely `unary_union` 前先 `buffer(15m)` 使 ≤30m 间隙的楼粘连,`unary_union` 后取**包含定位点的连通分量**,再消 buffer。
4. 异常出口:定位点不落在任何分量内(定位偏出楼群)→ 取距定位点最近的分量,并在预览中标记 `low_confidence`。

## 轮廓生成

`unary_union(入选楼面)` → `buffer(20m).buffer(-20m)` 填缝 → 取最大外环 → `simplify(0.0001°)` → ring 坐标 WGS84→GCJ02 → 输出 `{community_id, rings, source: "osm-building", meta: {building_count, area_ha, low_confidence}}`。

坐标转换:标准 WGS84↔GCJ02 互逆对,内联实现(约 20 行,业内通用公式),落盘值与现有 polygons 文件(已 GCJ02)同口径;实现时用既有 142 个小区中任一点位对照验证偏差 <5m。

## 预览 HTML

模板字符串内联生成,数据以 `const DATA = {...}` 嵌入:候选轮廓(每小区一色 40% 透明)、定位点(黑)、既有轮廓(source=osm,灰描边,从 polygons 文件读)、每个候选 meta(建筑数/公顷/low_confidence)。高德 JS key 读取 `apps/housing-map/.env.local` 的 `NEXT_PUBLIC_GAODE_MAP_KEY`,读不到则在页面顶部黄条提示手动填。勾选状态存 localStorage,导出按钮生成 `selected.json` 下载。

## --apply

读 selected.json → 对每个候选 `POST {--api}/api/map/boundaries/import`,头 `X-Admin-Token`(env `HOUSING_ADMIN_TOKEN` 或 `--token`)。逐条处理,打印每条通过/拒绝原因;任何网络错误中止并列出已完成/未完成清单(接口幂等,重跑安全)。

## 回滚

脚本不直接写 polygons 文件;落盘一律走接口(原子写+备份在接口侧)。输出目录整体可删。

## 测试

- 合成 fixture:两个相邻楼群(间隙 25m / 40m)+ 定位点,断言聚类分簇正确。
- hull:合成楼块断言外环包含全部楼、面积 < bbox 面积的一半(防粘出巨块)。
- 转换:GCJ02→WGS84→GCJ02 往返误差 <1e-6°。
- Overpass 客户端:mock HTTP,断言镜像 fallback 顺序与缓存命中不发请求。
