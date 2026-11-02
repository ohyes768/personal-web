# 周线管线契约（后端）

> 来源：10-29-index-trends 与 11-02-index-trends-weekly 任务。
> `backend/index-trends` 的取数 → 校验 → 计算 → 发布 → 周报口径速查。
> Last verified: 2026-11-02

## Scope / Trigger

改周K取数、交易日历、周线模型、周报生成或存储结构前必读。

## 周与日历

- 周主键 `week_start` = 自然周**周一**（ISO），`week_end` = 周日；行情 `date` 是该周
  **实际最后交易日**，不是供应商的自然周结束日。
- 一周只有在**该周所有交易日 15:05 已过**时才算完成（`MARKET_CLOSE_CUTOFF`）。
  只看到本周日才能判断本周还有没有交易日——查到今天会把"周一只收一天"误判成整周结束。
- 日历用 `pandas_market_calendars` 的 SSE 日历（覆盖 2005-04 起），越界抛
  `CalendarUnavailableError`；**绝不退化成"周一到周五都是交易日"**。
- 整周休市是正常市场事实，缺失行情是异常，两者不能互相冒充。

## 取数与校验

- 腾讯 `fqkline` 返回行顺序是 `[日期, 开, 收, 高, 低, 量]`（收盘在第 3 位）。
- 周K 必须覆盖 2005-04 起点；日线必须覆盖最近应已收盘的会话日；
  周K 收盘与当周最后交易日日线交叉校验（容差 0.01）。
- 校验失败抛异常并记录失败状态，**旧成功快照仍可读**，不静默降级成"正常但数据旧"。

## 计算与发布

- 坐标 `x = (week_start − origin).days / 7`；整周休市在坐标上留间隔，
  **不能用 `enumerate(closes)` 压缩掉时间**。
- 宽度 `2 × deviation`；算法版本 `lrc-ltb-week-v1`（月线算法与基准不变）。
- 模型 kind：`trailing_10y_weekly`、`since_inception_weekly`、`historical_fixed_10y_weekly`。
- 一次刷新在内存算完后**单事务发布**周K/日线/模型/元数据；模型按 `model_id` 只插入不覆盖。
- `snapshot_id` 由截止周、周线哈希与模型 ID 派生；哈希必须带周坐标。

## 周报

- 幂等键 `指数|ISO自然周|weekly`；同周已 `sent` 的报告（含旧月线）不重发。
- 周五 19:00（Asia/Shanghai）发送；15:05 前手动触发不占用本周投递名额。
- `business_status`：`normal` / `no_trading` / `data_error`；缺行情、缺模型、日历越界
  都是 `data_error`，**不能写成休市或 normal**。
- 位置变化只和同一周线 kind 的上一自然周快照比较，并拆成价格 / 模型 / 时间推进；
  首次周线报告不与旧月线位置比较。

## Storage

- 周线表与月线表完全隔离（`weekly_bars` / `weekly_models` / `weekly_data_meta`）；
  旧月线表保留为历史档案，**不把 `months` 列改装成周数**。
- 结构变更走 `schema_migrations` 版本化、幂等迁移；旧库重复迁移不丢数据。

## Wrong vs Correct

Wrong：用序号代替周坐标；把"日历确认全周休市"写成"缺失行情"；把进行中的周算进拟合；
把月线位置当上周周线位置。
Correct：坐标用自然周；休市与缺数据分开；进行中的周只展示；跨周期不比较。
