# 宏观各 Tab init/update 指标与成败规则对齐

> **已合并**进 `08-29-macro-us-treasury-empty-update`（2026-08-29）。本目录归档，不要再实现。完整路径表、hasData、串行规则以留下的任务 `prd.md` 为准。

## Goal

每个曲线图 Tab 的「初始化历史数据」覆盖本页画出的全部指标，「更新数据」覆盖同一套指标。多端点 Tab 一律串行、全部成功才算成功并置灰。用户点开任一数据 Tab 单独初始化，该页曲线都能出来，不必先去别的 Tab 点一遍。

## 背景

归档任务 `08-29-macro-unify-write-buttons` 只统一了按钮外壳（文案、daily 置灰、`onSuccess` 刷图）。指标清单和聚合成败规则没对齐：

- 中美利差/汇率初始化只打美债 + 汇率 history，漏中债；更新已经有中债。
- 利率利差初始化和更新都只有中债 + TED，漏 DR007 和美债（图上有 DR007、美债 3M）。
- 中美利差、流动性、利率用 `Promise.all` +「任一成功即成功」，会撞 `routes.py` 全局 `_is_updating`，按钮可能置灰但缺线。
- 市场情绪已经串行、全部成功才置灰（符合 `.trellis/spec/backend/global-macro-fin/backend/data-sources.md`）。
- 商品、股指各打一个端点，清单本身齐。

已锁定的产品决策：

1. 中美利差/汇率保留完整美债曲线（3M / 2Y / 10Y），页名不改。
2. 美债 3M、中国 10Y 允许两页都画：中美利差看跨境长端 + 美国曲线；利率利差看短端对照 + 国内曲线。
3. 哪个 Tab 画出这条线，初始化和更新都写这条线（重叠 CSV 两边都打，增量幂等）。
4. 多端点一律串行，任一步失败整体失败、不置灰。

## Requirements

### R1 展示即写入

每个数据 Tab 的初始化调用该页全部曲线对应的 `/fetch/*/history`；更新调用同一套 `/update/*`。重叠指标两边都写。

| Tab | 图上曲线 | 初始化 | 更新 |
|-----|----------|--------|------|
| 中美利差/汇率 | 美债 3M/2Y/10Y、中国 10Y；美元指数、USD/CNY、USD/JPY、USD/EUR | `/fetch/us-treasuries/history` → `/fetch/exchange-rates/history` → `/fetch/china-bonds/history` | `/update/us-treasuries` → `/update/exchange-rates` → `/update/china-bonds` |
| 利率利差 | DR007、SOFR、美债 3M、TED；中国 10Y、中国 10Y-2Y | `/fetch/china-bonds/history` → `/fetch/ted-spread/history` → `/fetch/dr007/history` → `/fetch/us-treasuries/history` | `/update/china-bonds` → `/update/ted-spread` → `/update/dr007` → `/update/us-treasuries` |
| 流动性/风险 | VIX、TGA、HIBOR | `/fetch/vix/history` → `/fetch/tga/history` → `/fetch/hibor/history` | `/update/vix` → `/update/tga` → `/update/hibor` |
| 商品 | 金/银/原油/铜 | `/fetch/commodities/history` | `/update/commodities` |
| 股指 | 恒生/上证/标普/纳指/道指 | `/fetch/indices/history` | `/update/indices` |
| 市场情绪 | 成交额、换手率、融资余额、北向成交额、南向净流入 | `/fetch/volume-turnover/history` → `/fetch/margin/history` → `/fetch/fund-flow/history` | `/update/volume` → `/update/turnover` → `/update/margin` → `/update/fund-flow` |

端点顺序固定，与上表箭头一致。单端点 Tab（商品、股指）保持一次 POST。

### R2 串行且全部成功

- 多端点初始化/更新：`await` 串行，禁止 `Promise.all`。
- 任一步 `success === false` 或抛错 → 整体失败，按钮不置灰，展示该步错误。
- 全部成功才返回成功，InitButton 永久置灰、RefreshButton 置灰到明天 00:00，并 `onSuccess` 重拉当前 Tab。
- 抽取共用串行 POST helper，六个 Tab 的聚合函数都走它，禁止再写「任一成功」返回值。

### R3 hasData 用本页全量、按线齐全判断

`hasData` 用 `fullData`（不要用时间范围切片后的 `data`），避免 1M 视图把初始化按钮误置灰。

多序列 Tab 用 **AND**：本页关键序列都有长度才视为已初始化。单端点 Tab 可用代表序列（商品看黄金、股指看标普）作为该次写入已完成的代理。

| Tab | hasData |
|-----|---------|
| 中美利差/汇率 | 美债 10Y 有长度 **且** 汇率（美元指数）有长度 **且** 中国 10Y 有长度 |
| 利率利差 | DR007 **且** TED **且** 中国 10Y **且** 美债 3M 有长度 |
| 流动性/风险 | VIX **且** TGA **且** HIBOR（已是 AND，保持） |
| 商品 | `commodities.gold` 有长度 |
| 股指 | `indices.SPX` 有长度 |
| 市场情绪 | volume **且** turnover **且** fund_flow.north_deal_amount 有长度（融资余额可短，不挡初始化；margin 有独立 history，有长度更好但不作为硬条件） |

### R4 按钮外壳与特例不变

继续复用 `InitButton` / `RefreshButton`。文案仍是「初始化历史数据」/「更新数据」。各 Tab 独立 `storageKey`。信号首页、对比不加写数按钮。

## 约束

- 不改后端 `routes.py` 全局锁、不拆锁、不新增聚合后端端点。
- 不改 `scheduler.json`；调度继续按组跑 `/update/*`。
- 不改图表布局、曲线集合、Tab 名称（曲线划分已锁定；可读性属 `08-29-macro-chart-readability`）。
- 不改 `/api/macro/data/{tab}` 读数契约。
- 不恢复德债/日债 Tab。
- 不把 JPY/EUR 从中美利差图拿掉（本次只改写入）。

## 验收标准（Acceptance Criteria）

- [ ] **AC1** `economicApi.initHistory` 串行打美债、汇率、中债三个 history；漏任一则 `rg` 对 `initHistory` 看不到 `china-bonds` 即失败。
- [ ] **AC2** `economicApi.initRatesHistory` / `updateRates` 串行包含中债、TED、DR007、美债四步；源码中这两个函数没有 `Promise.all`。
- [ ] **AC3** `initLiquidityHistory` / `updateLiquidity` 串行 VIX→TGA→HIBOR；源码中没有 `Promise.all`。
- [ ] **AC4** 市场情绪、商品、股指的端点清单不回退；市场情绪仍串行且全部成功才成功。
- [ ] **AC5** `apps/macro/src/lib/modules/economic/api.ts` 中数据 Tab 的 init/update 聚合不再出现 `Promise.all`，也不再出现「任一成功即视为成功」。
- [ ] **AC6** 六个数据 Tab 的 `hasData` 符合 R3；利率/中美利差用 `fullData` 且 AND。
- [ ] **AC7** 信号首页、对比仍无 Init/Refresh 按钮。
- [ ] **AC8** 浏览器：利率利差点初始化，网络面板按序出现 4 个 history；中途若某步失败，按钮保持可点、不置灰。成功后本页能看到 DR007 与美债 3M（CSV 写入成功的前提下）。

## 范围外

- 拆掉或细化全局 `_is_updating` 锁。
- 调度任务改组或改 cron。
- 图表可读性、拆子图、改颜色（`08-29-macro-chart-readability`）。
- 从中美利差图移除美债 3M/2Y 或 JPY/EUR。
- 对比页/信号首页加写数按钮。
- 后端新增「一键 init 本 Tab」聚合路由。
