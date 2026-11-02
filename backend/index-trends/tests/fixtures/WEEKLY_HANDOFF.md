# 周线后端交接说明（第 1、2 节 → 第 3 节）

本文件记录第 1、2 节已落地的字段与契约，供第 3 节（API/周报）直接使用。
权威合同仍是 `design.md` 第 5 节；本文说明实现与该表的对应关系。

## 1. 已实现的模块

| 模块 | 职责 |
|---|---|
| `src/core/weeks.py` | 周标识（周一 YYYY-MM-DD）、ISO 周标签、自然周坐标、窗口区间、固定窗口定义；`WeeklySample` / `WeeklyBar` / `WeeklySeries` 纯数据结构 |
| `src/data/trading_calendar.py` | `TradingCalendar` 协议（可注入 `sessions(start, end)`）、`StaticTradingCalendar`（测试）、`XshgTradingCalendar`（pmc SSE）、`CalendarUnavailableError` |
| `src/core/regression.py` | `fit_weekly_channel(xs, closes, multiplier)`（显式 x），`WEEK_ALGORITHM_VERSION = "lrc-ltb-week-v1"` |
| `src/core/weekly.py` | 选样与模型构建：`build_trailing_weekly_model` / `build_since_inception_weekly_model` / `build_fixed_weekly_models` / `WeeklyModelBuilder` |
| `src/core/models.py` | 周线 kind 常量、`WeeklyModelRecord`、`weekly_data_hash`（含周坐标）、`build_weekly_model_id` |
| `src/data/validate.py` | `build_weekly_series`（完整周判定 + 缺失/休市/越界区分）、`check_weekly_daily_consistency`、`expected_last_complete_week` |
| `src/services/store.py` | 周线表 + 版本化迁移 + `publish_weekly_snapshot`（单事务） |
| `src/services/trend_service.py` | `WeeklyTrendService`（三段分离）、`compute_snapshot_id` |

## 2. design.md 第 5 节字段对照

### model 层（`WeeklyModelRecord` → API `model`）

| design §5 | 实现字段 | 状态 |
|---|---|---|
| timeframe:week | `timeframe`（恒为 `"week"`） | 已实现 |
| sample_count | `sample_count` | 已实现 |
| calendar_window_start/end | `calendar_window_start` / `calendar_window_end` | 已实现 |
| fit_start/end（周一） | `fit_start` / `fit_end`（YYYY-MM-DD 周一） | 已实现 |
| fit_last_trade_date | `fit_last_trade_date`（该周实际最后交易日） | 已实现 |
| data_cutoff_week | `data_cutoff_week`（最近完整周的周一） | 已实现 |
| model_id | `model_id` | 已实现 |
| coefficients | `coefficients`（slope/intercept/deviation） | 已实现 |

额外已实现（API 可直接暴露或自行组装）：`index_code`、`kind`、`algorithm_version`、
`data_hash`、`multiplier`、`calculated_at`。

### data_status 层（`weekly_data_meta` → API `data_status`）

| design §5 | 实现来源 | 状态 |
|---|---|---|
| state | 第 3 节按 `data_cutoff_week` 与 `expected_cutoff_week` 比较得出 | **待第 3 节实现** |
| data_cutoff_week | `weekly_data_meta.data_cutoff_week` | 已实现 |
| expected_cutoff_week | `validate.expected_last_complete_week(calendar, now)` | 已实现（需第 3 节调用） |
| expected_close_date | `validate.expected_last_session(calendar, now)` | 已实现（需第 3 节调用） |
| daily_last_date | `store.load_daily_quotes(limit=1)` | 已实现（需第 3 节调用） |
| captured_at | `weekly_data_meta.captured_at` | 已实现 |
| reason | 第 3 节按异常类型给出（`calendar_unavailable` / `missing_data` / …） | **待第 3 节实现** |
| snapshot_id | `weekly_data_meta.snapshot_id` | 已实现 |

补充：`weekly_data_meta.last_error` / `last_error_at` 记录最近一次刷新失败，
**不改动**已发布的 `captured_at` / `data_cutoff_week` / `snapshot_id`（旧快照仍可读）。

### chart bars 层（`weekly_bars` → API `bars`）

| design §5 | 实现字段 | 状态 |
|---|---|---|
| week_start | `weekly_bars.week_start` | 已实现 |
| date（实际末交易日） | `weekly_bars.date` | 已实现 |
| open/close/high/low | 同名列 | 已实现 |
| partial | `weekly_bars.is_partial`（1=进行中周） | 已实现 |

读取：`store.load_weekly_bars(include_partial=False)` 取完整周，
`store.load_partial_weekly_bars()` 取进行中周。

### 其余 chart / history / status / refresh 层

`channel series`（weeks 含休市时间槽）、`fit_boundary_week`、`extension_series`、
`extend_note`、`history window`、`status`、`refresh` 均属第 3 节，本节未实现。

第 3 节需要的两个纯计算已在本节提供：
- `validate.expected_last_complete_week(calendar, now)` → `expected_cutoff_week`
- `validate.expected_last_session(calendar, now)` → `expected_close_date`
- `core.weekly.fixed_window_observation_end(series, window)` → `observation_end_week`
  （名义区间后 3 年内、已有完整数据的最后一周；无观察期数据时 None）

### 与前端并行会话的契约一致性

前端会话（apps/index-trends/lib/types.ts）独立写出的类型镜像与本节实现
**字段名完全一致**，可直接对接：
`trailing_10y_weekly` / `since_inception_weekly` / `historical_fixed_10y_weekly`、
`timeframe`、`sample_count`、`fit_last_trade_date`、`calendar_window_start/end`、
`data_cutoff_week`、`snapshot_id`、`reason`、`observation_end_week`、
`fit_boundary_week`、`projection_week`、`weekly_count`。

## 3. 第 3 节可直接使用的服务入口

```python
from src.services.trend_service import WeeklyTrendService, compute_snapshot_id

svc = WeeklyTrendService(store, now_fn=..., calendar=...)   # calendar 可注入
result = svc.refresh_sync(client)      # 三段：取数校验 → 纯计算 → 事务发布
# result: success / message / data_cutoff_week / data_cutoff_trade_date /
#         weekly_count / new_models / snapshot_id
```

读模型：
```python
store.latest_weekly_model("000300", "trailing_10y_weekly")
store.weekly_model_by_cutoff("000300", "trailing_10y_weekly", "2026-10-26")
store.list_weekly_models("000300", kind=None)
```

## 4. 周线 kind 与月线 kind 的隔离

| 月线 kind | 周线 kind |
|---|---|
| `trailing_120m` | `trailing_10y_weekly` |
| `since_inception` | `since_inception_weekly` |
| `historical_fixed_120m` | `historical_fixed_10y_weekly` |

月线表（`monthly_bars` / `models` / `data_meta`）保留为历史档案，未改动；
周线用独立表，`months` 列未被改装成周数（周线用 `sample_count`）。

## 5. report_settings 迁移的触发时机（重要）

`report_settings.model_kind` 的月线→周线映射**不在建库时**执行，
而是在**周线快照首次发布时**（与快照同一事务，见
`Store.publish_weekly_snapshot`）执行。原因：建库即迁移会让尚未切换管线的库
被提前改写，导致月线 API（`/api/report-settings`）读到周线 kind 而报错。

- 迁移版本：`002_report_settings_weekly_kind`，记录在 `schema_migrations`
- 保留 `enabled` / `channel` / `send_cron` / `index_code`
- 幂等：已是周线 kind 的行不动
- 旧 `reports` 行不改写（`model_kind` 仍为月线 kind，原文保留）
- 第 3 节切换 API 后，可显式调用 `store.migrate_report_settings_to_weekly()`

## 6. 已知的日期/语义事实（供第 3 节参考）

1. **供应商周K 的 date 语义**：该周最后一个**已收盘**交易日。
   完整周的 date = 日历该周最后交易日；进行中的周 date = 最近已收盘交易日。
   校验以"该周全部会话已收盘"为完整判据。
2. **整周休市**：供应商仍会返回一根 K 线（收盘是上一周的重复值）。
   日历确认该周无会话 → 丢弃该 K 线，保留时间槽（坐标留间隔）。
   真实数据中 `2012-01-23` 那周就是这种情况。
3. **周归属按 week_end（周日）**落入 `[start_inclusive, end_exclusive)` 判定。
4. **近10年**：上界 = 最近完整周的 week_end 次日；下界 = 上界减 10 个日历年
   （2 月 29 日落到非闰年取 2 月最后一天）。样本数按实际有交易周计
   （当前 fixture：512 周），不是固定 520 周。
5. **成立以来**：从含 2005-04-08 发布周的首条有效周K 起（`2005-04-04` 那周）。
6. **固定窗口**：名义区间 10 年、3 年步进（`fixed-2005-04` 等 4 个），
   `stable_id` 用名义起点命名，数据更新不变。
7. **未完成周不参与拟合**，但落库为 `is_partial=1`，供图表展示。

## 7. 尚未实现 / 归属第 3 节

- API 响应组装（`/api/index-trends/*` 的周线字段）
- 周报生成与投递（`report_service.py` 改周线口径）
- 位置变化的"价格影响 / 模型影响 / 时间推进影响"三项拆分
- `business_status` 与投递 `status` 的分离
- 旧 URL `model=trailing_120m/since_inception` 的别名解析与 `replace`
- 周报 `snapshot_json` 落库（列已建，写入逻辑在第 3 节）

## 8. 预存的失败（非本次引入）

`tests/test_report.py::test_report_generated_and_sent` 在本次改动前即失败
（用 `git stash` 验证过）：报告服务按"日线缺失"判整周休市，
未区分"整周休市"与"数据未到位"。属第 3 节范围。
