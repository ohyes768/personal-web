# Design：采集扩展覆盖萧山接壤板块

## 依据

research/tmsf-plate-mapping.md：板块清单敲定为 tmsf 口径 {钱江世纪城, 开发区, 宁围, 闻堰}，
候选 285 小区（<300 阈值）。行政街道「盈丰」≈ tmsf「钱江世纪城」。

## 结构决策

### 1. 清单过滤（fetch_tmsf_binjiang_communities.py）

`BINJIANG_PREFIX = "滨江"` 前缀匹配改为函数：

```python
XS_PLATES = {"钱江世纪城", "开发区", "宁围", "闻堰"}

def in_collect_scope(district: str | None, subdistrict: str | None) -> bool:
    if district == "滨江":
        return True
    return district == "萧山" and subdistrict in XS_PLATES
```

脚本名与输出文件名**不改**（binjiang_communities.json 沿用，PRD 明确不拆双套文件）。
normalize 逻辑不动（arearmk 已带 district/subdistrict）。

### 2. 坐标（fetch_gaode_coordinates.py）

地址构造 `杭州市滨江区{name}` → `杭州市{district}{name}`（按小区的 district 字段）。
萧山小区用地理编码可能失准的比例更高（研究样本 ~20% 外），抓完后以
`is_in_scope` 统计落点；围栏外的进 fix_mislocated 清洗队列而非直接丢（保留人工核查余地）。

### 3. 属性三件套（property_type / product_attrs / community_age）

均为"逐小区详情页"模式：对新 community_id 全量跑，输出 merge 进现有 json。
keyed by community_id，新记录覆盖旧记录（与 merge_snapshot_rows 同策略）。

### 4. POI（fetch_gaode_pois.py）

现在按滨江围栏抓；改为按 `is_in_scope` 多边形（滨江 ∪ 三板块）。
萧山板块 POI 密度高于滨江（钱江世纪城商圈），配额先估：polygon 搜索按网格分片，分片数 ≈ 面积比 × 现有滨江分片数。执行前打印预估调用量，超 5000 次/日配额的 30% 先报告。

### 5. 轮廓（OSM residential 链路）

fetch_osm_polygons 的 bbox 与 fetch_osm_layers 同步（已扩）→ convert_osm_residential
→ extract_binjiang_polygons → build_merged_polygons 全链重跑。
extract/build 的"滨江"围栏判断改 is_in_scope。

### 6. 刷新时长

新增 ~200 小区后全量刷新时长 = 滨江实测 × (N_新/N_滨江)。现有滨江 ~150 小区刷新
约 X 分钟（实测后填）。>15 分钟则 scheduler cron 双周化（改 REFRESH_CRON 一处）。

## 不改的

- refresh.py / select_refresh_targets / is_real_community：小区入库后自动纳入
- 评分算法、文件名、前端（子任务 3）
