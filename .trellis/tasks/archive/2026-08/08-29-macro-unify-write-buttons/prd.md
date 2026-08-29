# 宏观页数据 Tab 写入 UX 统一

## Goal

宏观经济页上所有**数据 Tab** 的写入交互一致：能拉历史（初始化）、能点「更新数据」、成功后按日置灰。**信号首页**和**对比**保持只读特例，不加写数按钮。

## 背景

### 已确认（代码，2026-08-29 复核）

5 个 Tab 已经共用 `InitButton` + `RefreshButton`：

| Tab | 初始化 | 更新 | 置灰 |
|-----|--------|------|------|
| 中美利差/汇率 | `initHistory`（美债+汇率 history） | `updateUsTreasuriesAndRates` | daily → 明天 00:00 |
| 流动性/风险 | `initLiquidityHistory`（VIX+TGA+HIBOR） | `updateLiquidity` | 同上 |
| 利率利差 | `initRatesHistory`（中债+TED） | `updateRates` | 同上 |
| 商品 | `initCommoditiesHistory` | `updateCommodities` | 同上 |
| 股指 | `initIndicesHistory` | `updateIndices` | 同上 |

组件规则（`InitButton.tsx` / `RefreshButton.tsx`）：

- **初始化**：成功后永久置灰（`localStorage` + `hasData` 兜底）。过程中「初始化中...」禁用。
- **更新**：`cadence="daily"`，成功后置灰到明天本地 00:00，文案「下次更新：YYYY-MM-DD」。过程中「更新中...」禁用。失败不置灰。
- **初始化成功不会刷图**：`InitButton` 没有 `onSuccess`；只有更新成功才 `refreshKey++`。

3 个 Tab 没有这套按钮：

- **市场情绪**：前端仍无按钮，文案还写「盘后调度、无需手动刷新」。
- **对比**：按 `indicators` 读已写入的 CSV，不自己写数。
- **信号首页**：读 `/api/macro/signal` 与日频快照，不写 CSV。

### 市场情绪后端（`08-29-baostock-volume-turnover` 已归档，端点已落地）

| 动作 | 端点 | 说明 |
|------|------|------|
| 历史回补成交额+换手率 | `POST /api/macro/fetch/volume-turnover/history` | 一次写 `volume.csv` + `turnover.csv`；query `start_date` 默认 `2010-01-01`，`end_date` 默认昨天。已从误放的 `/update/.../history` 改到规范前缀 `/fetch/` |
| 当日增量成交额 | `POST /api/macro/update/volume` | BaoStock，近 10 日窗口 |
| 当日增量换手率 | `POST /api/macro/update/turnover` | 同上 |
| 当日增量融资余额 | `POST /api/macro/update/margin` | 仍是 akshare 当日点，**没有** history 端点 |

对方任务范围外写明：融资余额历史回补另开；前端改动不在那个任务。

全局 `_is_updating` 锁：同一时刻只能跑一个 `/update/*`。流动性 Tab 的 `Promise.all` +「任一成功」会让另外两条请求拿到 `UPDATE_IN_PROGRESS`。市场情绪不要复制这个写法，更新要**串行**。

### 交互不一致（要修）

1. 市场情绪没有初始化/更新按钮。
2. 更新按钮文案不统一：「更新数据」vs「更新中美利差/汇率」等。
3. 初始化按钮文案不统一：「初始化历史数据」vs「初始化商品数据」等。
4. 点初始化成功后图表不自动重拉。
5. 各 Tab `hasData` 判断口径不同（有的看 `dates.length`，有的看单条序列）。

## Requirements

### R1 数据 Tab 都有同一套两个按钮

下列 6 个 Tab 都必须同时有 `InitButton` + `RefreshButton`：

- 中美利差/汇率
- 流动性/风险
- 利率利差
- 商品
- 股指
- 市场情绪

按钮组件继续复用现有 `InitButton` / `RefreshButton`，不另写一套。

### R2 置灰规则统一

- 初始化：成功后永久置灰；后端已有该 Tab 数据时同样置灰。
- 更新：全部 `cadence="daily"`；点击中禁用；成功后置灰到明天本地 00:00；失败保持可点。
- 各 Tab 继续用**独立** `storageKey`，互不影响。

### R3 文案统一

- 初始化：一律「初始化历史数据」（tooltip 或旁注可写具体数据源）。
- 更新：一律「更新数据」。

### R4 写成功后当前 Tab 重拉

`InitButton` 增加 `onSuccess`（与 `RefreshButton` 对齐）。初始化或更新成功都调用页级 `onRefreshSuccess`，当前 Tab 出 loading 并重拉 `/api/macro/data/{tab}`。

### R5 信号首页 / 对比保持特例

- **信号首页**：不加初始化/更新按钮。
- **对比**：不加初始化/更新按钮。对比仍按已选指标读数；其它 Tab 更新成功后的 `refreshKey` 行为保持现有（对比可见时清对应缓存再拉）。

### R6 市场情绪接线（消费已落地端点）

`economicApi` 新增封装，`MarketSentimentTab` 接上两个按钮。去掉「无需手动刷新」文案。

- **初始化**：`POST /api/macro/fetch/volume-turnover/history`（一次回补成交额+换手率，默认 `start_date=2010-01-01`）。成功后置灰并 `onSuccess` 刷图。
- **更新**：串行 `POST /update/volume` → `/update/turnover` → `/update/margin`（避开全局更新锁）。全部成功才算成功；中途失败展示错误、不置灰。
- **hasData**：`volume` 或 `turnover` 有长度即视为已初始化（融资余额没有 history，不能拿它挡初始化）。
- **不新增** `/fetch/margin/history`。融资余额历史仍靠每日 `update/margin` 累积。

### R7 历史端点走规范前缀 `/fetch/*/history`

`POST /api/macro/update/volume-turnover/history` 改为 `POST /api/macro/fetch/volume-turnover/history`。函数名改为 `fetch_volume_turnover_history`。不保留旧路径别名。日常增量仍是 `/update/volume`、`/update/turnover`。

## 约束

- 不改信号首页、对比页的读数契约（`/api/macro/signal`、`/api/macro/data/comparison?indicators=`）。
- 不改调度 `scheduler.json` / n8n 盘后任务；按钮是手动补写，调度继续跑。
- 不恢复德债/日债 Tab。
- 不把宏观信号并进 `/data/{tab}`。
- 不改 BaoStock 取数口径；历史端点路径已改为 `/fetch/volume-turnover/history`，handler 逻辑不变。
- 与进行中的 `08-28-macro-per-tab-data` 分工：那个任务管读数拆分/日期轴/loading；本任务只管写入按钮 UX。两边都改 `page.tsx` / 各 Tab 时注意冲突。
- 与 `08-29-macro-chart-readability` 分工：那个任务管图表可读性，不改更新按钮。

## 验收标准（Acceptance Criteria）

- [x] **AC1** 6 个数据 Tab 都看得到「初始化历史数据」和「更新数据」两个按钮；信号首页、对比看不到这两个按钮。
- [x] **AC2** 任一数据 Tab 点「更新数据」：请求进行中按钮禁用并显示「更新中...」；成功后置灰到明天 00:00，文案含「下次更新」；刷新页面后仍置灰。（`RefreshButton` cadence=daily + 独立 storageKey；未做浏览器实地点击）
- [x] **AC3** 点「初始化历史数据」成功后按钮永久置灰；该 Tab 图表自动重拉。CSV 已有该 Tab 数据时初始化按钮直接是已初始化态。（`InitButton.onSuccess` → `refreshKey++`）
- [x] **AC4** 6 个 Tab 的更新互不影响置灰状态（各用各的 `storageKey`）。
- [x] **AC5** 市场情绪点「更新数据」串行打 `POST /update/volume`、`/update/turnover`、`/update/margin`；成功后该 Tab 重拉 `/api/macro/data/market-sentiment`。
- [x] **AC6** 现有 5 个 Tab 的更新/初始化仍打原来的 API，不回退。
- [x] **AC7** 信号首页仍只读快照；对比仍按 `indicators` 读，没有写数按钮。
- [x] **AC8** 市场情绪点「初始化历史数据」打 `POST /api/macro/fetch/volume-turnover/history`。
- [x] **AC9** `POST /fetch/volume-turnover/history` 存在；旧路径 `/update/volume-turnover/history` 已删除。日常增量仍是 `/update/volume`、`/update/turnover`。

## 范围外

- 信号首页手动刷新快照。
- 对比页自己触发底层 CSV 更新。
- 改 `cadence` 为 monthly（全部保持 daily）。
- gzip / Cache-Control / 按 Tab 读数（`08-28-macro-per-tab-data`）。
- 图表可读性（`08-29-macro-chart-readability`）。
- 利率 Tab 初始化是否补美债 3M / DR007（现有缺口，另开任务）。
- BaoStock 实现与 volume/turnover 口径（已归档的 `08-29-baostock-volume-turnover`）。
- 融资余额 history 端点（对方任务明确另开；akshare 全量接口存在但当前只写当日点）。
- 拆成 `/fetch/volume/history` + `/fetch/turnover/history`（一次 BaoStock 会话同时写两份 CSV，与 commodities 一样用一个 fetch 名）。
- 给旧 `/update/volume-turnover/history` 留兼容别名（无调度/前端调用方，规范禁止两套命名）。
- 修复流动性 Tab 并发打三个 update 撞全局锁（可另开；本任务只保证市场情绪串行）。

## Open Questions

（无。融资余额初始化：见 R6，本任务不补 history。）

## Notes

- 用户原话：全站统一，信号首页/对比是特殊的。历史端点由其它任务补；本任务接线，并把误放在 `/update/` 下的 history 改到 `/fetch/`。
- 置灰是浏览器 `localStorage`，不是后端锁。本任务不改成服务端锁。
- 实现提交：`26538b4`。浏览器端到端点击未跑；验收按源码对照。
