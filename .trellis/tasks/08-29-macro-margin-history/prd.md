# 融资余额历史回补接口

## Goal

补上融资余额全量历史回补，让市场情绪图的融资余额曲线从 akshare 已有的 2010-03-31 起有完整日频序列；点「初始化历史数据」会一并写入成交额、换手率和融资余额，而不是只靠每日 `update/margin` 攒点。

## Background

- 市场情绪 Tab 读 `margin.csv` 的 `margin_balance_yi`（亿元，沪+深合计）。读数契约已存在，缺的是历史写入。
- 已有 `POST /api/macro/update/margin`：`margin_service.fetch_today()` 只取沪、深最后一行后落库。调度继续用这个端点做当日增量。
- 没有 `POST /api/macro/fetch/margin/history`。《数据更新端点规范》已标明「暂无」。
- 数据源已验证：`akshare.macro_china_market_margin_sh()` / `_sz()` 一次调用即返回 2010-03-31 起全量（沪约 3983 行 / 深约 3785 行，单位**元**，÷1e8 成亿元）。与当日更新同源，不换数据源。
- `08-29-baostock-volume-turnover` 把本能力标成范围外。`08-29-macro-unify-write-buttons` 已把 Init/Refresh 接到市场情绪 Tab，初始化只打 `/fetch/volume-turnover/history`。
- 沪、深行数不同，必须按**日期对齐**再相加；禁止按行号/iloc 对齐（skill 脚本 `fetch_margin_history` 的按行对齐不能照搬）。
- `fetch_today` 与历史回补共用列名识别、单位换算；只是历史要对齐全表而不是取最后一行。
- 前端已有：`economicApi.initMarketSentimentHistory` 只打 volume-turnover；`hasData` 为 `volume || turnover` 有长度；`updateMarketSentiment` 已串行 volume → turnover → margin。全局 `_is_updating` 锁要求 history 也必须串行。

## Requirements

### R1 全量历史端点

- 新增 `POST /api/macro/fetch/margin/history`，遵循现有 `/fetch/{xxx}/history` 命名与并发锁。
- 一次拉取沪、深全表，按日期对齐后合计融资余额（元 → 亿元），写入 `margin.csv`。
- 同日覆盖 `keep=last`，重复调用幂等、不产生重复行。
- 日常增量仍是 `POST /api/macro/update/margin`，路径与响应不变，调度无感知。

### R2 对齐与口径

- 两市按日期 outer join；缺一侧的日期用 0 再合计（「两市合计」在单边无数据日不丢行、不把单边当成两市）。
- 只写 `margin_balance_yi`，不新增融券余额等列。
- 单位与当日更新一致：akshare 元 ÷1e8 → 亿元，保留 2 位小数。

### R3 前端初始化接线

- `economicApi.initMarketSentimentHistory` 串行：`POST /fetch/volume-turnover/history` → `/fetch/margin/history` → `/fetch/fund-flow/history`（后一步是资金流向任务已接线的端点；三条共用 `_is_updating` 锁，不能并行）。任一步失败则整体失败、不置灰；已写入的部分可幂等重跑。
- 不改 RefreshButton / `updateMarketSentiment`（当日三条增量已串行）。
- 不改 InitButton / RefreshButton 组件，不改 `hasData`（仍为 `volume || turnover` 有长度），不换 `storageKey`。
- 已有几天融资余额日更点时，由操作员删 CSV、清浏览器 `localStorage` 后再点初始化（见 Notes），本任务不做自动识别/换 key。

### R4 测试与文档

- 历史合并、单位、幂等有单测；mock akshare，不真连外网。
- 更新《数据更新端点规范》端点清单和 `data-sources.md`：补上 `/fetch/margin/history`，初始化改为两条 history 串行。

## 范围外

- 不改当日 `update/margin`、调度 `scheduler.json`、读数 `/api/macro/data/market-sentiment`。
- 不改图表可读性（`08-29-macro-chart-readability`）。
- 不把成交额/换手率与融资余额合成一个 history 端点。
- 不给旧路径留别名。
- 不重做市场情绪 Tab 的按钮 UX。
- 不改 `hasData` 启发式，不加「补融资余额」独立按钮，不换 storageKey。

## Acceptance Criteria

- [ ] **AC1** `POST /api/macro/fetch/margin/history` 成功后 `margin.csv` 有 2010-03-31 起的日频序列（量级约数千行），无重复日期。
- [ ] **AC2** 沪、深日期不完全重合时仍按日期对齐合计；缺一侧记 0，不按行号错位相加。
- [ ] **AC3** 写入单位为亿元，与现有 `update/margin` 同一量级；同日再跑 `update/margin` 只覆盖该日、不打乱历史。
- [ ] **AC4** 重复调用 history 不增加重复行（keep=last）。
- [ ] **AC5** 进行中的 `/update/*` 或其它 `/fetch/*/history` 会返回 `UPDATE_IN_PROGRESS`。
- [ ] **AC6** `python -m pytest tests/test_margin.py -v` 通过；历史路径 mock akshare。
- [ ] **AC7** 《数据更新端点规范》与 `data-sources.md` 清单含 `/fetch/margin/history`，并写明初始化串行 history（含融资余额）。
- [ ] **AC8** 市场情绪点「初始化历史数据」串行打 `/fetch/volume-turnover/history` → `/fetch/margin/history` → `/fetch/fund-flow/history`；全部成功才置灰并重拉图表。
- [ ] **AC9** 中途失败（含第二步失败）按钮保持可点，不把半截成功当成已初始化。

## Notes

- 回补会覆盖 `margin.csv` 已有同日点；CSV 可能不进 git，覆盖不可逆。
- 规范默认起点是 `settings.historical_start_date`（2000-01-01）；本数据源实际从 2010-03-31 才有值，过滤早于数据源起点的空窗即可。
- 手动重跑初始化（本机现网只有几天日更点时）：
  1. 删 `backend/macro/data/` 下 `volume.csv`、`turnover.csv`、`margin.csv`（只删 `margin.csv` 不够：`hasData` 看成交额/换手率，按钮仍置灰）。
  2. 浏览器控制台执行 `localStorage.removeItem('last_initialized_macro_market_sentiment')`。
  3. 打开市场情绪 Tab，点「初始化历史数据」。
