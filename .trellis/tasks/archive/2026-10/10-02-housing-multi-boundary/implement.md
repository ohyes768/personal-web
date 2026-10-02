# Implement：围栏多边形化

> Task: 10-02-housing-multi-boundary · 前置：PRD + design 已评审

## 执行清单（按序）

1. **拉萧山三街道边界** → 验证：盈丰/宁围/闻堰 polyline 拿到，点数合理（抽稀后各 ≤ 2000 点）
   - 写 `scripts/fetch_gaode_district_boundary.py`（一次性，读 _gaode_config.py key）
   - `GET /v3/config/district?keywords=<街道名>&subdistrict=0&extensions=all&key=...`
   - polyline `lng,lat;lng,lat` → `[[lng, lat], ...]`，Dou-Peucker 或均匀抽稀
   - 盈丰查不到时按 design fallback 顺序处理，结果记录到 research/gaode-district.md
   - 输出 Python 字面量写入 `src/core/boundary.py` 的 `XIAOSHAN_BORDER_BOUNDARIES`

2. **boundary.py 多围栏重构** → 验证：test_boundary 新用例通过
   - 提取 `_point_in_polygon`；新增 `XIAOSHAN_BORDER_BOUNDARIES` / `SCOPE_BOUNDARIES` / `is_in_scope`
   - `is_in_binjiang` 语义不变（改调 `_point_in_polygon`）

3. **transit.py 切换** → 验证：test_transit 全绿
   - 5 处 `is_in_binjiang` → `is_in_scope`；`clip_to_binjiang` → `clip_to_scope`
   - `boundary_points()` → 围栏集合总点数；docstring 更新

4. **测试更新** → 验证：pytest 全绿
   - test_boundary.py：334 断言保留；新增三街道围栏存在性（点数 ≥ 30）、`is_in_scope` 用例（滨江腹地点 True / 盈丰-钱江世纪城点 True / 闻堰点 True / 板块外萧山点（北干/义桥）False / 杭州主城 False）
   - test_transit.py：既有滨江裁剪用例不动（回归锚）；新增一条"萧山板块内线路段被保留"用例（构造跨盈丰的多段线）
   - test_api.py:126 `boundary_points == 334` → 按新总数改（或改为 ≥ 334 的断言 + 精确值注释）

5. **地铁数据重采** → 验证：`/api/map/transit` 返回含萧山板块站点（如 钱江世纪城/盈丰路/闻堰 相关站），滨江段与改造前一致
   - 定 scope bbox（按四围栏实测 bounds 加 margin）
   - 改 fetch_osm_layers.py BBOX → 跑 `transit_routes transit_stops` → convert_osm_transit.py → data/ 落盘
   - 前后对比：改造前先抓一份 `/api/map/transit` 响应存 research/，改后 diff 滨江部分

6. **收尾**
   - spec 更新（housing-map-admission.md 围栏一节）
   - commit：`feat(housing-map): 围栏多边形化，接入萧山盈丰/宁围/闻堰板块边界`

## 验证命令

```bash
cd backend/housing-map
uv run python -m pytest tests/ -v          # 全绿（含新用例）
uv run python -m uvicorn src.main:app --port 8096 &
curl -s localhost:8096/api/transit | python -m json.tool | head -40   # 人工核对萧山站点
```

## 回滚点

- 步骤 1-4 纯代码，git revert 单 commit 即回滚
- 步骤 5 数据文件重采覆盖 git 内文件，`git checkout -- data/` 恢复
