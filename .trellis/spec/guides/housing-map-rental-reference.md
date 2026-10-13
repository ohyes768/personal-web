# Housing-Map 租金参考与租售比契约

> 任务的实现层契约（上游采集见 [housing-map-fang-rentals.md](./housing-map-fang-rentals.md)，
> 后台任务/发布模式同源见 [housing-map-auctions.md](./housing-map-auctions.md)）。
> 改租金统计口径、映射台账、刷新任务或看板租金列前必读。

## 1. Scope / Trigger

- 触发：修改 `src/services/rental_reference/*`（statistics/storage/refresh）、`src/api/rental_routes.py`、前端 `rental-*`/`use-rental-*`、看板租金三列。
- 数据流：fang 租金样本 → 映射台账归并 → rental_reference 统计/存储 → 6 条 API → 详情标签 + 看板三列。

## 2. Signatures

```python
# storage.py（原子发布；路径全部参数化，生产默认 data/rentals/）
publish_run(rentals_dir, batches, *, run_id=None, report=None, cancel_event=None) -> PublishResult
    # PublishResult: published, run_id, reason('all_failed'|'cancelled'|None),
    #                adopted / carried_over / absent: tuple[str, ...]
load_current(rentals_dir) -> dict | None   # {run_id, published_at, communities{...}, degraded} 或 None
RentalPublishLock   # OS 文件锁 rentals_dir/rental_publish.lock；锁文件保留不删，OS 释放

# refresh.py（后台任务；线程内生命周期自管理，FastAPI 侧 asyncio.to_thread 包装）
RentalRefreshService(rentals_dir, mappings_path, *, fetch_factory=FangClient,
                     max_pages=10, delay=2.0, timeout=20.0, details=True, max_errors_kept=20)
    .start() -> dict   # RefreshAlreadyRunning→409 / NoVerifiedMappings→422 / MappingFileError→503
    .cancel() -> dict  # RefreshNotRunning→409；cancelling 直到线程退出→cancelled
    .status() -> dict / .shutdown(timeout=30) -> bool
load_verified_mappings(path) -> list[tuple[source_id, community_id]]  # 仅 source='fang' 且 status='verified'
```

## 3. Contracts

### 3.1 关联数据库与旧台账（踩过坑）

运行时关联以 `data/rental_sources.sqlite3` 为准，JSON 仅一次性迁移；页面确认/改绑/解除契约见 [租金来源管理](../backend/housing-map/backend/rental-sources.md)。旧数据卷缺 JSON 时从镜像 seed 导入，不能每次启动覆盖用户关联。

旧 JSON 格式：

```json
{ "version": 1, "mappings": [ { "source": "fang", "source_community_id": "...",
  "community_id": "...", "source_name": "...", "source_address": "...|null",
  "verified_at": "...", "status": "verified", "notes": "证据摘要+来源URL" } ] }
```

> **Warning**: 顶层**必须**有 `"version": 1`，否则 `load_verified_mappings` 判结构损坏 →
> summary/detail 503、POST refresh 503。2026-10-12 联调真实踩过（核验代理只写了
> `mappings` 键）。手工编辑台账后先跑 `load_verified_mappings` 验证。

### 3.2 API（对外路径经 nginx `/api/map/*` 剥前缀 → `/api/*`，无新增 nginx 规则）

| 方法 | 路径 | 语义 |
|---|---|---|
| GET | `/api/rentals/summary?area_band&bedrooms` | `{success,data:{area_band,bedrooms,summaries:[670条]}}` |
| GET | `/api/communities/{id}/rentals?area_band&bedrooms&view=valid\|excluded&page&page_size` | 分组汇总+明细分页；未知 ID 404，未映射 200+availability |
| GET | `/api/rentals/refresh` | 无任务 `data:null`；否则对外 job |
| POST | `/api/rentals/refresh` | 202 / 409 已运行 / 422 无映射 / 503 台账损坏；**无任何 URL 参数**，限制是服务配置 |
| DELETE | `/api/rentals/refresh` | 触发取消；无活动任务 409 |

- 枚举（前后端已互锁，勿单方改）：`area_band: all|lt90|90to144|gte144`；`bedrooms: all|1|2|3|4plus`。
- summary 条目：`community_id, availability, last_refresh, sample_count, captured_at, unit_rent_yuan_m2_month, annualized_gross_yield_pct`（缺失一律 `null`，禁 NaN/Infinity）。
- **并存语义**："旧数据可用 + 最近抓取失败" = `availability:'available'` + `last_refresh:{status:'failed',error}`，不是单独枚举。
- 对外 phase 映射（服务内部→对外）：crawling/publishing→running；done 且 carried_over+absent 全空→succeeded；done 但有缺席→partial_failed；其余直通。终态 = succeeded/partial_failed/failed/cancelled/interrupted。

### 3.3 availability 判定优先级（顺序敏感）

1. 台账无 verified 映射 → `unmapped`
2. 发布版本无该小区：最近刷新 failed → `source_failed`，否则 `no_samples`
3. 快照 >30 天 → `stale`（yield 强制 null，明细照常）
4. 口径内有效样本 0 → `no_samples`；<3 → `insufficient_samples`
5. 否则 `available`

### 3.4 统计口径（前端三列/详情/排序全部依赖）

- 仅整租住宅、面积/月租为正、排除合租/疑似分割；排除带理由枚举，excluded 明细可查看。
- 先来源 listing ID 去重；同小区+房型+面积+租金(+楼层)全同 → 疑似重复标记，不计样本数。
- 分组 = 房型 × 面积段；**"全部房型"= 该面积段合并合格样本重算**，绝不是房型中位数求平均。
- 单位租金 = 逐房源 月租/面积 的中位数（不是 中位月租÷中位面积）。P25-P75 作用在单位租金。
- 年化毛收益% = unit_rent × 12 ÷ sale_unit_price × 100；租售比 N = sale_price ÷ unit_rent。售价口径（signed/listing）与日期透传；缺售价/stale → yield null。
- **detail 与 summary 消费同一 `select_valid`+`group_stats`**（有测试锚定），改统计只改 statistics.py 一处。

### 3.5 发布语义（部分失败混合版本）

- 每小区 status ∈ {complete, empty_ok} 才采用新数据；truncated/partial_detail/list_failed → 保留旧样本与原 captured_at（`origin='carried_over'`），无历史则 absent。
- 全部失败 / 取消任何阶段 → **不切指针**；已写一半批次目录留在盘上供诊断。
- `current.json` 指针原子切换（tmp+os.replace）；损坏/悬空指针 → `load_current` 返回 None 不抛。
- job 状态持久化 `rentals/refresh_job.json`，进程重启：running→interrupted（仅本进程无线程时）；锁 sidecar 永不按年龄删除（防误杀存活 CLI 发布者）。

## 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 台账缺 version / 结构非法 | 503（summary/detail/POST） |
| 台账不存在 | 422（POST）；summary/detail 全部 unmapped |
| 未知 community_id（不在小区表） | 404 |
| 已映射但从未采集成功 | 200 + source_failed |
| 样本 <3 的组 | rent_reference 全 null，仅明细 |
| 非法 area_band/bedrooms | 422（Literal 校验） |
| 重复 POST / 无任务 DELETE | 409 |

## 5. Good/Base/Bad

- Good：3 小区采集成功 → adopted 全量、看板风雅钱塘 61.8 元/㎡/月 + 2.12%参考 + n=3。
- Base：部分小区截断 → 混合发布（成功新数据+失败沿用旧版）、刷新按钮显示"成功 X / 失败 Y"。
- Bad（禁止）：为凑样本把合租/疑似分割计入；用 0 代替缺失；口径间混排收益率。

## 6. Tests Required

后端 261 passed（`--basetemp` 项目盘）：统计 26（单位换算/分组边界 89.9/90/143.9/144/合并≠均值/P25P75 插值/不足3/缺售价/过期30d）、采集 run 15（五态/取消唤醒/进度）、存储 15（原子指针/全失败/混合/空页/取消竞争/损坏容错/锁互斥）、refresh 19（互斥/取消/持久化/重启恢复/CLI 锁冲突）、API 44（availability 全形状/phase 全枚举/域白名单/NaN 序列化）。前端 26 passed（node:test + renderToStaticMarkup；排序缺失沉底、终态判定、链接域）。改任一层必须全量回归。

## 7. Wrong vs Correct

### Wrong
```python
# 手工维护台账只写 mappings，缺 version → 全站租金接口 503
{ "mappings": [...] }
# 排序把缺失当 0：0 租金小区混进收益排名
value = summary.annualized_gross_yield_pct ?? 0
```

### Correct
```python
{ "version": 1, "mappings": [...] }          # 结构校验通过
# 前端：缺失 null → 显示 '—' 且排序永远沉底（升降序一致）
compareNumericMissingLast(a, b, order)       # null 一律 > 任何数值
```

## 已知坑（排查实录 2026-10-12）

1. **看板小区范围 ≠ 小区全量**：DashboardPage 收到的 communities 已被主组件
   `propertyTypes`（默认 住宅/别墅/排屋）过滤（670→377）。**控制入口在地图 tab 侧栏**
   "物业类型"勾选（跨 tab 联动）。风雅钱塘世纪花园源数据 `property_type='商贸'`，
   默认看板不可见——排查时表现为"排序不生效/搜索 0 行"，实为行根本不在表里。
2. **preview 起服务与 curl 排查混叠**：preview_stop 半关闭状态下 GET 可能返回旧态；
   疑似状态丢失先重启后端再下结论。
3. **detail 的 `bedrooms` 字段**：4plus 合并口径后端输出 `bedrooms: 4` +
   `bedrooms_filter: '4plus'`；前端如需"4居及以上"文案用后者渲染。

### Unified source check before web refresh (2026-10-14)
The directory-backed web flow now includes source checking/discovery before crawling. It retains the existing phase enum and adds `stage` plus optional `association` counts. No mappings is not a 422 when a directory is available: checking can finish with review tasks without publishing any data. Discovery/review cannot change asking-rent statistics or make stale/rebound snapshots valid. The legacy standalone mapping-only caller retains its no-mappings error.
