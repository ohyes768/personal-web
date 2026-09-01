# 数据 Tab 写入对齐：指标清单、串行成败、增量空窗

## Goal

六个数据 Tab 点「初始化 / 更新」时：本页画出的指标全部覆盖；多端点串行且全部成功才置灰；日度增量在外部 API 成功但没有新观测（周末/尚未发布）且 CSV 已有 last_date 时视为已是最新。外部 API 真失败返回原始错误，不再伪装成「未能获取到任何新数据」。用户点开任一数据 Tab 单独初始化，该页曲线都能出来。

本任务合并了原 `08-29-macro-tab-write-align`（指标清单 + hasData）。该目录已归档，不再单独实现。

## 背景

- 用户 2026-08-29（周六）在中美利差点「更新数据」，看到「美国国债数据增量更新失败: 未能获取到任何美债新数据」，按钮没有「下次更新」置灰。
- `RefreshButton` 只在 `res.success` 时写 localStorage 并置灰到明天 00:00；失败保持可点。组件不改。
- `routes.py` 全局 `_is_updating`：同一时刻只能跑一个 fetch/update。`data-sources.md` 已禁止 `Promise.all`。市场情绪已串行；中美利差 / 流动性 / 利率仍 `Promise.all`，且聚合写成「返回第一条」而不是「全部成功」。
- 美债 `_fetch_us_treasuries` 与 `FredService.fetch_exchange_rates` 把异常吞成空 Series。增量在 `last_date+1 ≤ 今天` 时仍拉数，全空则 `UPDATE_FAILED`。DR007 已把区间无新数据当成功。
- 商品、股指是单端点，前端无并发问题，但增量同样是「API 成功全空 → raise」。
- 归档 `08-29-macro-unify-write-buttons` 只统一了按钮外壳。指标清单没对齐：中美利差初始化漏中债；利率 init/update 漏 DR007 和美债（图上有 DR007、美债 3M）。

已锁定的产品决策：

1. 中美利差/汇率保留完整美债曲线（3M / 2Y / 10Y），页名不改。
2. 美债 3M、中国 10Y 允许两页都画。
3. 哪个 Tab 画出这条线，初始化和更新都写这条线（重叠 CSV 两边都打，增量幂等）。
4. 多端点一律串行，任一步失败整体失败、不置灰。

信号首页、对比仍只读。

## Requirements

### R1 增量空窗视为已是最新

外部 API **调用成功**、区间内无有效观测（empty 或无 `last_valid_index`），且 `get_last_date` 非空 → `success=true`、message 含「已是最新」，不写 CSV。无底库仍失败。全量 `/fetch/*/history` 全空仍失败。

端点（共用 `_has_observations` + `_empty_increment_is_current`）：

- `/update/us-treasuries`、`/update/exchange-rates`、`/update/china-bonds`
- `/update/vix`、`/update/tga`、`/update/hibor`、`/update/ted-spread`
- `/update/commodities`、`/update/indices`

DR007 已符合，不重复改逻辑。资金流向是近 10 日窗口重写，空批语义不同，不纳入本 helper。欧债/日债月度、n8n `POST /api/macro/update` 仍范围外。

### R2 外部异常不得吞成空数据

- `_fetch_us_treasuries`、`FredService.fetch_exchange_rates` 不再 per-series 吞异常。
- VIX/TGA/TED/HIBOR 失败路径已上抛，只改空窗分支。

### R3 展示即写入，多端点串行且全部成功

在 `api.ts` 抽 `postSerial(paths)`：依次 `directClient.post`，任一步 `success === false` 或抛错立即返回该响应；全部成功才返回成功（Init 永久置灰、Refresh 置灰到明天 00:00，并 `onSuccess` 重拉）。禁止 `Promise.all` 和「任一成功」。

| Tab | 图上曲线 | 初始化 | 更新 |
|-----|----------|--------|------|
| 中美利差/汇率 | 美债 3M/2Y/10Y、中国 10Y；美元指数、USD/CNY、USD/JPY、USD/EUR | `/fetch/us-treasuries/history` → `/fetch/exchange-rates/history` → `/fetch/china-bonds/history` | `/update/us-treasuries` → `/update/exchange-rates` → `/update/china-bonds` |
| 利率利差 | DR007、SOFR、美债 3M、TED；中国 10Y、中国 10Y-2Y | `/fetch/china-bonds/history` → `/fetch/ted-spread/history` → `/fetch/dr007/history` → `/fetch/us-treasuries/history` | `/update/china-bonds` → `/update/ted-spread` → `/update/dr007` → `/update/us-treasuries` |
| 流动性/风险 | VIX、TGA、HIBOR | `/fetch/vix/history` → `/fetch/tga/history` → `/fetch/hibor/history` | `/update/vix` → `/update/tga` → `/update/hibor` |
| 商品 | 金/银/原油/铜 | `/fetch/commodities/history` | `/update/commodities` |
| 股指 | 恒生/上证/标普/纳指/道指 | `/fetch/indices/history` | `/update/indices` |
| 市场情绪 | 成交额、换手率、融资余额、北向成交额、南向净流入 | `/fetch/volume-turnover/history` → `/fetch/margin/history` → `/fetch/fund-flow/history` | `/update/volume` → `/update/turnover` → `/update/margin` → `/update/fund-flow` |

端点顺序固定。单端点 Tab 保持一次 POST。不改 `RefreshButton` / `InitButton` / `storageKey`。市场情绪路径不回退，只改走 `postSerial`。

### R4 hasData 用本页全量、按线齐全判断

`hasData` 用 `fullData`（不要用时间范围切片后的 `data`）。多序列 Tab 用 **AND**。单端点 Tab 用代表序列。

| Tab | hasData |
|-----|---------|
| 中美利差/汇率 | 美债 10Y **且** 美元指数 **且** 中国 10Y 有长度 |
| 利率利差 | DR007 **且** TED **且** 中国 10Y **且** 美债 3M 有长度 |
| 流动性/风险 | VIX **且** TGA **且** HIBOR |
| 商品 | `commodities.gold` 有长度 |
| 股指 | `indices.SPX` 有长度 |
| 市场情绪 | volume **且** turnover **且** `fund_flow.north_deal_amount` 有长度（融资余额不挡初始化） |

### R5 测试与文档

- pytest：美债空窗/抛错/无底库；其余 R1 端点参数化各一条「有 last_date + 空观测 → 已是最新」。不真连外网。
- 前端无测试框架：`rg "Promise.all" apps/macro/src/lib/modules/economic/api.ts` 无命中（除注释外）；`initHistory` 含 china-bonds；`initRatesHistory` / `updateRates` 含 dr007 与 us-treasuries。
- 规范 + `data-sources.md`：空窗语义；六个数据 Tab 多端点必须串行，并列出 R3 路径表。

## 约束

- 不改后端全局锁、不拆锁、不新增 Tab 级聚合路由。
- 不改 `scheduler.json`。
- 不改图表布局、曲线集合、Tab 名称（可读性属 `08-29-macro-chart-readability`）。
- 不改 `/api/macro/data/{tab}` 读数契约。
- 不恢复德债/日债；不把 JPY/EUR 从中美利差图拿掉。

## 范围外

- 不补本机 `.env`、不代跑全量 FRED 初始化。
- 不改调度 cron、`RefreshButton` 失败不置灰 UX、信号首页、对比。
- 不改 n8n 综合 `/update`、欧债/日债月度、资金流向 10 日窗空批语义。

## 验收标准（Acceptance Criteria）

- [ ] **AC1** 美债 CSV 有 last_date、FRED 空观测：`POST /update/us-treasuries` success、已是最新、CSV 不变。
- [ ] **AC2** FRED 抛错：美债增量 `UPDATE_FAILED`，message 含原始错误。
- [ ] **AC3** 美债无 CSV 且全空：仍失败。
- [ ] **AC4** `POST /fetch/us-treasuries/history` 全空仍失败。
- [ ] **AC5** 中美利差 / 流动性 / 利率 的 init 与 update 均为串行；中途失败不打后续、对应按钮不置灰。
- [ ] **AC6** 上述 Tab 全部步骤成功（含已是最新）后更新按钮显示「下次更新：YYYY-MM-DD」至明天本地 00:00；初始化成功仍永久置灰。
- [ ] **AC7** 进行中的其它 fetch/update 仍 `UPDATE_IN_PROGRESS`。
- [ ] **AC8** R1 清单内除美债外的端点：有 last_date 且 API 成功无新观测 → success 已是最新。
- [ ] **AC9** 商品、股指 Tab 仍是单端点；空窗走 AC8，前端不引入 `Promise.all`。
- [ ] **AC10** `api.ts` 中数据写入不再使用 `Promise.all`，也不再「任一成功」；市场情绪只改走 `postSerial`，路径不回退。
- [ ] **AC11** pytest 通过；规范与 `data-sources.md` 已更新（含 R3 路径表）。
- [ ] **AC12** `initHistory` 串行含中债 history；`initRatesHistory` / `updateRates` 串行含中债、TED、DR007、美债四步。
- [ ] **AC13** 六个数据 Tab 的 `hasData` 符合 R4，均读 `fullData`。
- [ ] **AC14** 信号首页、对比仍无 Init/Refresh 按钮。
- [ ] **AC15** 浏览器：利率利差点初始化，Network 按序 4 个 history；成功后本页能看到 DR007 与美债 3M（CSV 写入成功的前提下）。

## Notes

- 「已是最新」与「增量写入成功」对按钮都是 `success=true`。
- 本机真拉美债需要 `.env` 的 `FRED_API_KEY` 和一次初始化。
- 已置灰的 localStorage key 不改名；若以前「假成功」置灰，需手动 `removeItem`。
