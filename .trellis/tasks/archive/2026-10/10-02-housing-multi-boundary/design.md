# Design：围栏多边形化

> Task: 10-02-housing-multi-boundary · PRD 见同目录 prd.md

## 边界与契约

### boundary.py 新结构

```python
# 保留
BINJIANG_BOUNDARY: list[list[float]]          # 334 点不动（历史约束解除）
XIAOSHAN_BORDER_BOUNDARIES: dict[str, list[list[float]]]   # {"盈丰": [...], "宁围": [...], "闻堰": [...]}

# 派生
SCOPE_BOUNDARIES: list[tuple[str, list[list[float]]]]      # [("滨江", BINJIANG_BOUNDARY), *XIAOSHAN...]

# 函数
_point_in_polygon(lng, lat, polygon) -> bool   # 从 is_in_binjiang 提取的通用射线法
is_in_binjiang(lng, lat) -> bool               # 保留，滨江单区语义（未来前端区筛选用）
is_in_scope(lng, lat) -> bool                  # 任一围栏命中
```

**萧山围栏来源**：高德行政区 API（`/v3/config/district?keywords=<街道>&subdistrict=0&extensions=all`），polyline 解析 + 抽稀（滨江当时同模式：拉取后硬编码进 boundary.py）。新增一次性脚本 `scripts/fetch_gaode_district_boundary.py`，从 `_gaode_config.py` 读 key，输出可直接粘贴的 Python 字面量。

**已知风险**：盈丰街道 2021 年才从宁围拆出，高德可能查不到。Fallback 顺序：
1. `盈丰街道` 查到 → 盈丰 + 宁围 两个多边形
2. 查不到 → 用老口径 `宁围街道`？不可行（高德返回的是拆分后边界）→ 改用 keywords=宁围镇 或直接用萧山区 polygon 手动截取世纪城范围（最后手段，需人工核对）
3. 实测结果写进本任务 research/，若需最后手段则升级到用户确认

### transit.py 改造（唯一消费方）

| 现状 | 改为 | 说明 |
|------|------|------|
| `is_in_binjiang` 4 个调用点（seg_boundary_intersect×2、clip_to_binjiang×2、stops 过滤×1，共 5 处） | `is_in_scope` | 裁剪算法/二分逻辑零改动 |
| `clip_to_binjiang()` | 改名 `clip_to_scope()` | 无外部引用（已核实 routes.py 只 import build_subway_data/boundary_points） |
| `boundary_points()` 返回 334 | 返回围栏集合总点数 | 仅 meta 消费，前端不用（已核实）；test_api.py 断言同步改 |
| `build_subway_data` docstring"滨江" | 更新为双区表述 | |

### 地铁数据重采

- `fetch_osm_layers.py`：`BBOX` 常量改为覆盖 滨江+三板块 的整体 bbox（约 `30.13,120.11,30.30,120.33`，实现时按街道 polygon 实测 bounds 定），只重跑 `transit_routes transit_stops` 两图层（green/water/pois/roads 无消费方，不动）
- `convert_osm_transit.py`：bbox 无关（raw→geojson 全量转换），零改动
- 裁剪发生在服务端 `build_subway_data`，新围栏自动生效

## 数据流（改后）

```
Overpass(bbox 扩大) → binjiang_osm_transit_*.json → convert_osm_transit.py(不变)
  → binjiang_transit_routes/stops.geojson → build_subway_data + is_in_scope
  → /api/map/transit（滨江段 + 萧山板块段）
```

## 权衡

- **三街道独立多边形 vs 融合成一个"萧山板块"多边形**：选独立。省融合算法，`which_district` 类需求（子任务 3 区筛选）天然支持，围栏集合元素即业务单元。
- **围栏硬编码 vs 运行时拉 API**：选硬编码（与滨江 334 点同模式）。围栏是低频变化的基础数据，运行时依赖高德 API 反而引入启动风险。
- **文件名 binjiang_***：不改（parent PRD 排除项）。

## 回滚

单 commit 独立可回滚；数据文件重采前备份（`*_滨江期.bak` 后缀或 git checkout 即可，jsonl/json 均已入库）。
