# 创业板50 纳入指数趋势与 PB/PE 分位

## Goal

在 index-trends 上能看到**创业板50（399673）的 PB 分位（主）** 与 **PE 分位（辅）**，用于定投加减档决策：分位越低投越多，PB 分位过半停止新增，高位回落配合 IRR 止盈。

> 范围修正（2026-11-20，用户明确）：**创业板50 不要走势通道**，只做 PB/PE 分位。
> 它不采行情、不算模型、不出通道图；通道类接口返回 409。

## Background（已核实的现状）

**服务是单指数，不是配置化多指数。**

- `src/services/trend_service.py:68-70` 三个模块常量 `INDEX_CODE="000300"` / `SYMBOL="sh000300"` / `INDEX_NAME="沪深300"`，被刷新、模型计算、状态、概览全链路引用。
- 存储层没有指数维度：`monthly_bars`、`daily_quotes`、`data_meta`、`weekly_bars`、`weekly_data_meta` 的主键都不含 index_code；`models` / `weekly_models` 表有 `index_code` 列，但读接口不接受筛选，`load_weekly_bars()` 之类的读方法直接返回全表。
- 起点写死：`core/models.py:32` `INCEPTION_MONTH="2005-04"`，`trend_service.py:81` `WEEKLY_INCEPTION_WEEK="2005-04-04"`（沪深300 发布周）。

**估值只有一条口径。**

- `src/data/lixinger.py:30-38`：只取 `pe_ttm.mcw` 与 `pe_ttm.y10.mcw.cvpos`，metric 常量 `VALUATION_METRIC="pe_ttm_mcw"`、窗口 `"y10"` 均为模块级单值。
- `index_valuations` 表已有 `(index_code, source, metric, window)` 列，扩指标有位置；但 `valuation_fetch_meta` 是 `id=1` 单行设计，多指数会互相覆盖失败状态。

**数据源。**

- 行情：腾讯 `fqkline`，按 symbol 取（`data/provider.py`）。创业板50 对应 `sz399673`。
- 估值：理杏仁 `cn/index/fundamental`。官方文档核实：分位窗口为 `y1/y3/y5/y10/y20/fs(上市以来)`，**没有 y6**；PB 与 PE 共用同一套 `[指标].[窗口].[加权].[统计]` 语法，PB 为 `pb.mcw` / `pb.y10.mcw.cvpos`。
- 创业板50：发布 2014-06-18，样本 50 只，半年调样，派氏加权。10 年窗口基本等于其全部历史。

**前端。**

- 只有 `apps/index-trends/lib/api.ts:27-33` 四处硬编码 `/indices/000300/...`，页面组件本身按返回值渲染。

## Requirements

**R1 指数注册表** — 服务从「单指数常量」变为「可枚举的指数列表」，至少含 沪深300（000300 / sh000300 / 2005-04）与 创业板50（399673 / sz399673 / 2014-06）。指数名、代码、腾讯 symbol、起始周/月集中一处定义。

**R2 行情隔离** — 两个指数的月K / 周K / 日线 / 模型 / 元数据互不覆盖；一个指数刷新失败不得影响另一个的可用数据与状态。

**R3 创业板50 只做估值** — 399673 不提供走势通道：`IndexDef.has_trend=False`，行情刷新跳过它，`/chart` `/history` 返回 409，`/status` 返回 `reason=valuation_only`，估值走 `GET /api/indices/{code}/valuation`（不需要 `model`）。

**R3b 通道指数不受影响** — 000300 的周线能力（近10年、成立以来、固定10年窗口）与起点边界保持原样。

**R4 估值双指标** — 每个指数可采集 PE-TTM 与 PB 两条分位，落库按 `(index_code, metric, window)` 区分；失败状态按指数隔离。

**R5 展示** — 页面上能看到该指数的 PB 分位与 PE 分位：当前值、数据日期（as_of）、采集状态（ok/stale/empty/error/disabled）；可切换指标。分位图形态见「待确认」。

**R6 不回归** — 000300 的现有接口与页面行为不变；无 Token 时照旧降级为 `disabled`，绝不把缺失当 0 分位。

## Acceptance Criteria

- [ ] `GET /api/indices` 返回两个指数条目，399673 含 code/name/symbol/inception。
- [ ] `GET /api/indices/399673/status` 返回 `available=false`、`reason=valuation_only`，且 `valuation.metrics` 仍有 PB 与 PE-TTM 两条。
- [ ] `GET /api/indices/399673/chart` 与 `/history` 返回 409；`GET /api/indices/399673/valuation` 不需要 `model` 参数即可取到两条分位。
- [ ] 每日行情刷新只遍历 `trend_index_codes()`（当前只有 000300）。
- [ ] `GET /api/indices/399673/status` 的 `valuation` 同时含 PB 与 PE-TTM 两条，各自有 percentile_pct、as_of、state。
- [ ] 刷新 399673 前后，000300 的周K行数与 weekly model_id 不变；反之亦然。
- [ ] 未配置 `INDEX_TRENDS_LIXINGER_TOKEN` 时 `valuation.state=="disabled"`，页面不出现 0 分位或假数据。
- [ ] `backend/index-trends` 的 pytest 全绿；`apps/index-trends` 的 `pnpm lint` 与 `tsc --noEmit` 通过。

## Out of Scope

- 不新增 创业板指（399006）、科创50、中证500 等其他指数（首个任务只做 399673）。
- 不做持仓记账、定投执行、收益回测。
- 不改 Hermes 周报投递内容；若要让创业板50 进简报，另开任务。
- 不引入新的行情或估值供应商。

## 已定口径

**分位窗口 = 10 年**（`y10`）。理杏仁直接提供 `pe_ttm.y10.mcw.cvpos` 与 `pb.y10.mcw.cvpos`，与现有沪深300 口径一致，零本地滚动计算。代价：与天弘官方策略的「PB 近 6 年分位」不严格可比——已知差异，接受。

## 待确认（不阻塞设计）

**R5 形态**：当前分位数值 + 近 10 年历史分位曲线（默认，见 design.md 第 4/6 节）。若只要当前数值，可砍掉 `index_valuation_history` 表与曲线接口、组件，工作量约减半。
