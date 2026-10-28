# design — 轮廓上传接口与前端展示

## 后端

- **路由文件**:`src/api/boundary_import_routes.py`(跟随 auction_routes/rental_routes 分文件惯例),main.py 挂载,前缀 `/api/map/boundaries`。
- **模型**(pydantic):`BoundaryItem{community_id: str, coordinate_system: Literal["gcj02"], rings: list[list[list[float]]], meta: dict | None}`、`ImportRequest{source: Literal["osm-building"], boundaries: list[BoundaryItem]}`;source 收窄为 osm-building,防误传其他来源。
- **鉴权**:startup 读 `HOUSING_ADMIN_TOKEN` 存 app state;缺失 → 路由直接 503("upload disabled");比较用 `hmac.compare_digest`。
- **校验链**(逐条独立 try,汇总响应):
  1. cid ∈ 展示小区集合(复用 load_display_communities 的 cid 集,构建一次)
  2. ring 点数 ≥3 且首点==尾点(允许自动闭合?不——严格拒绝,脚本侧负责闭合,避免静默修正)
  3. 环内抽样点 `boundary.is_in_scope` 通过(复用 core/boundary.py)
  4. shapely 面积 ≤1 km²(坐标按度算,换算近似:度² × cos(lat) × 111² 修正;或直接投影简化——用 pyproj?不引新依赖,用球面近似公式)
- **落盘**(`services/boundary_import.py`):
  - threading.Lock(单进程 uvicorn 足够)
  - 备份:`data/boundaries-backup/<UTC ts>.json`,超过 5 份删最旧
  - 合并:`{**原文件, cid: {"rings": ..., "source": "osm-building", **meta}}`;`_meta.sources` 追加 `"osm-building"` 描述条目(已有 sources 数组结构,追加去重)
  - 原子写:`json.dump` 到 `*.tmp` → `os.replace`;与 auction_store 手法一致
- **响应**:`{success: true, data: {accepted: [...], rejected: [{community_id, reason}]}}`(跟随仓库 API 信封惯例)。

## 前端

- `apps/housing-map/src/components/map/BinjiangMap.tsx`:现有 `boundary_source === 'osm'` 才画轮廓的判断 → `['osm','osm-building'].includes(...)`;`osm-building` 时 path 虚线(`strokeDasharray`)+ 常规填充色阶不变。
- types.ts:`boundary_source` 类型放宽为 `'osm' | 'shp' | 'osm-building'`。
- 验证方式:本地后端 data 塞一条 osm-building 样例(手工或脚本候选),地图页目检虚线;不为此建组件测试。

## 回滚

- 接口独立路由文件,摘除挂载即回滚;备份目录可手工还原 polygons 文件。
- 前端改动两个文件各一处,git revert 即可。

## 测试

- TestClient:401(错 token)/ 503(未配置)/ 各校验拒绝 / 合法写入 + 文件内容断言 / 幂等覆盖 / 备份生成。
- polygons 文件路径在测试中指向 tmp 目录(现有测试对 data 目录的处理方式照搬,如 test_auctions 的 fixture 惯例)。
