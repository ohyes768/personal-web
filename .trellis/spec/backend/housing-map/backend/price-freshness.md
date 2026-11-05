# Housing-Map 价格时效、双价投影与刷新契约

> 触发：改动价格读取投影、采集资格、刷新任务、评分市场分、租售比取价日期或前端价格展示前必读。
> 来源任务：11-04-housing-price-freshness（2026-11-04 实施并全量验证）。

## 1. 核心时效规则（src/services/price_policy.py，唯一实现）

- `SHANGHAI_TZ`、`MAX_DEAL_AGE_MONTHS = 6`：成交月份与当前上海月份月差 ≤6 有效（恰好 6 有效、7 过期）；未来月份无效。
- `STALE_AFTER_DAYS = 30`：对应价格超过 30 天未成功更新提示「超过30天未更新」，保留原采集日期；与 6 个月规则独立计算。
- 签名：`shanghai_today(today=None)`、`month_gap_from_today(month,*,today=None)`（解析失败 None）、`deal_month_is_current(month,*,today=None)`、`collection_stale(captured_on,*,today=None)`、`project_price_record(record,*,today=None)` → `{"price","month","captured_at","captured_date","source_url","stale","current","expired"}` 或 None。
- 未知/非法成交月份返回 None，不得用采集日期顶替月份。时间一律可注入 `today`；测试注入固定日期，禁止依赖执行当天。

## 2. 读取投影（data_loader.load_price_snapshots(path=None,*,today=None)）

- 兼容字段保留：`price/price_type/date`（有效签约价优先、挂牌兜底；无有效价时 `price=None`，但历史与套数照常返回）。
- 新槽：`deal / listing / history_deal / counts / refresh`，缺失一律 None。过期签约只进 `history_deal`；counts-only 快照（抓到首页只有套数）只贡献套数槽。
- 合并来源小区按价格类型**分别**选最新（按 `(crawled_at, snapshot_date)` 比较），与文件顺序无关。
- API 实际透出 `_public_price_entry` 恰为 `{price, month, captured_at, source_url, stale}`——**没有** `captured_date/current/expired` 键；前端采集日从 `captured_at` 截取，`history_deal` 槽位本身即过期证据。

### Wrong vs Correct：顶层套数字段已死

```python
# Wrong：读顶层 deal_count（批次 A 起恒不存在，市场分会静默变 None）
count = price.get("deal_count")
# Correct：走 counts 槽
count = (price.get("counts") or {}).get("count")
```

> 教训（质检实锤 High）：`scoring.py` 曾残留顶层 `deal_count` 读取导致全量小区 `market_score=None`。**移除投影字段后必须全仓搜索消费方**，不能只看 API 测试绿。

## 3. 采集资格与补齐（src/services/refresh.py）

- `collectible_plans`（all/missing/GET 计数共用同一实现）：`community_views.map_status=='displayed'`（蕴含 admitted+真实小区+覆盖内有效坐标）+ 排除 `new_house`/project + 全部 matched TMSF community 来源按来源去重。不读轮廓文件（缺轮廓仍采）；无台账返回空计划。
- `missing_plans`（补齐目标）：deal 与 listing 槽（仅当前有效价）**都为空**才算缺价；缺一种、或超 30 天未更新但仍有可用价，都不算。
- 轮内每个请求前 + 返回后轻量重查资格与绑定（`_still_collectible`）；撤销/换绑的小区跳过、结果不落盘、`processed` 计 skip 保证进度可达 total。
- **`processed` 按主小区递增**（与 `total`、updated/noData/failed/skipped 同单位），不按来源递增——否则合并小区（多来源）进度会 >100%。

## 4. 刷新 API

- `POST /api/refresh`，query：`mode=all|missing`（默认 all；定时任务复用默认 all）、`limit=0`（0=全量，服务端 clamp ≤500）。
  - 200：`{"success":true,"data":{"total":<小区数>,"mode":...,"backupFile":...|null}}`
  - 409：任务运行中，或目标为空（missing=「没有缺少价格的小区」/all=「没有可采集的已收录小区」）——空目标不产生任务
  - 422：mode 非法
- `GET /api/refresh`：`data` = job 全量 + `{eligible, missing}`（服务端每次全量重算，较重；**前端只在页面加载取一次**，轮询不重复取）。
- job 字段（前端轮询依赖）：`running, phase("idle|fetching|merging|done|error|cancelled"), mode, total, processed, okCount, errorCount, updated, noData, failed, skipped, retained, startedAt, finishedAt, error, result`。`okCount/errorCount` 是 updated/failed 的兼容别名。取消时 `phase="cancelled"` 且 `result=null`。
- 命名陷阱：**轮级统计键 camelCase（`noData`），outcome 枚举值 snake_case（`no_data`）**。所有入口（定时/全量/补齐）共用 running 互斥。

## 5. price_refresh_status.json（每小区刷新结果持久化）

顶层 `{community_id: 条目}`（读取侧要求条目带字符串 `outcome`，否则忽略）。条目字段：

```
community_id, mode, run_id, updated_at,
outcome: "updated|no_data|failed|skipped", partial: bool,
retained: bool, retained_reason: null|"fetch_failed"|"parse_failed"|"no_price_data"|"expired_only"|"ineligible",
retained_price_date: null|YYYY-MM-DD,
price_updated: bool, counts_updated: bool,
price_captured_at: null|ISO, counts_captured_at: null|ISO,
sources: {<sid>: {outcome, reason, partial, errors[]}}
```

- 轮级终态枚举 `succeeded|partial|failed|no_data|skipped`（取消走 job 的 `cancelled`，不产生 result）。
- `retained_price_date` = 旧快照保留价格记录的最新 `snapshot_date`；skipped 小区不计 retained。
- 套数与价格各自独立记录；**套数未成功获取不得更新套数采集时间，套数更新不得表述为价格更新**。

## 6. 发布边界

- 主快照原子发布：临时文件在目标目录、flush/fsync 后 `os.replace`，失败清理临时文件并保留旧快照；**每轮最多发布一次**。
- 无新记录不改主快照，但仍写刷新状态。
- CSV 是可重建导出：失败仅 warning（文案须含「主快照已发布」），不得误称主快照未变。`CSV_FIELDS` 现含 `trend_point_count`，不含 `sample_count/confidence_score`（JSONL dataclass 字段保留兼容旧读取，deal 行恒 `sample_count=0`、`confidence_score=null`）。
- 任务取消：不发布快照、不写状态文件，仅 job 记录取消尝试。

## 7. 评分消费方（scoring.py）

- 市场面签约套数走 counts 槽；无独立采集日期或超过 30 天未核验的套数**退出评分**（`calculate_score`/`calculate_all_scores` 可注入 `today`）。
- 价格本身不参与综合评分；过期成交不进当前价，也不进租售比（`rental_routes._sale_reference` 的 `price_date` 优先 `deal.month`，回退采集日）。

## 8. 前端（apps/housing-map）

- `src/lib/price-freshness.ts` 是价格数据的唯一读取归一化口（价格条目/counts/job/每小区状态/eligible-missing）；缺失字段不崩、不编造。
- `PriceDetails`：签/挂各一格（价格+所属月份+采集日+stale 角标），过期签约进「历史参考」行，无有效价显示「暂无近期价格」。
- `PriceRefreshControls`：双入口「刷新已收录」「补齐价格（N）」；N=0 禁用补齐；页面加载 GET 一次数量、running 时 3s 轮询 job、done 后重拉小区数据；终态展示 updated/noData/failed/skipped/retained。

## 9. 测试与验证

- 后端 `tests/test_price_freshness.py`（时效边界/双价/换绑合并）、`tests/test_refresh.py`（资格/互斥/取消/原子发布/CSV 失败/进度单位）。固定日期注入（如 TODAY=2026-11-15）。
- 前端 `tests/price-freshness.test.cjs`（lib 归一化 + 两组件 SSR），不请求真实上游。
- 验证命令（Windows）：backend/housing-map 下 `.venv/Scripts/python.exe -m pytest tests/ --basetemp=.pytest-tmp-price`；apps/housing-map 下 `node --test tests/*.test.cjs`、`npm run lint`、`npx tsc --noEmit`、`npm run build`。
