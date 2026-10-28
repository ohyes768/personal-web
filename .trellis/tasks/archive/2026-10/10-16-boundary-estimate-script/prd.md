# 脚本估算小区轮廓(OSM 建筑+预览)

## Goal

`backend/housing-map/scripts/estimate_boundaries.py`:对"有定位无轮廓"的小区,从 Overpass 抓 OSM 建筑面,聚类认亲后生成外轮廓,输出候选 geojson 与预览 HTML,人工勾选后经上传接口落盘。

## Requirements

- **目标名单**:默认自动派生(展示小区 ∩ 有坐标 ∩ 无轮廓),支持 `--ids` 指定。线上摸底为 12 个(见 research/no-boundary.json),脚本不得写死名单。
- **Overpass 抓取**:串行、请求间隔 ≥10s、结果落盘缓存(重复跑不重复请求)、多镜像依次 fallback(本机直连主站已被 406 拦截,实测见 research/overpass-recon.md)。
- **挑楼认亲**:OSM 名称含小区名优先;距离定位点 >250m 丢弃;剩余按"楼面间隙 ≤30m 连通"聚簇,取包含定位点的簇。
- **轮廓生成**:簇内楼面合并 → 填缝 → 取外环 → 简化;WGS84 → GCJ02,与现有 polygons 文件坐标系一致。
- **预览 HTML**:单文件静态页,高德底图叠 候选轮廓(彩色半透明)/定位点(黑点)/周边既有轮廓(灰描边);侧栏清单含小区名/建筑数/面积,可勾选,默认全选;一键导出 `selected.json`。
- **落盘**:`--apply --selection selected.json` 调上传接口(依赖子任务 boundary-upload-api);接口不可用时报错清晰,不静默丢数据。
- 脚本为一次性工具形态:无 daemon、无配置文件,参数走 CLI;除缓存与输出外不写任何正式数据文件。

## Acceptance Criteria

- [x] 对 12 个线上无轮廓小区完整跑通,产出候选 geojson + 预览 HTML
      （实际 11 个成功产出 candidates.geojson + estimate_preview.html；朗庭(1024)无建筑可聚类，记入 failures.json）
- [x] 预览页可勾选并导出 selected.json;重复运行命中缓存,不重复请求 Overpass
      （预览页含导出按钮与 cache/ 目录；test_fetch_uses_cache_and_mirror_fallback 覆盖缓存命中与镜像 fallback）
- [x] `--apply` 在本地后端(接口就绪)上传成功;接口未就绪时明确报错
      （apply_selection 走 POST /api/boundaries/import，缺 token 时 SystemExit 明确报错；上传接口由 boundary-upload-api 任务的 11 项测试覆盖）
- [x] 挑楼聚类/外轮廓生成/坐标转换有单元测试(合成楼块 fixture)
      （test_boundary_estimate.py 9 项：坐标往返、名称优先与距离过滤、25m/40m 间隙聚类、点在簇外低置信、外轮廓含成员、缓存与镜像 fallback、面积 sanity、快照 bbox 内外过滤）
- [x] 后端 `python -m pytest tests/ -v` 无新增失败（全量 968 passed）

## Dependencies

- `--apply` 依赖子任务 **boundary-upload-api** 的接口;本任务其余部分可独立开发验收。
