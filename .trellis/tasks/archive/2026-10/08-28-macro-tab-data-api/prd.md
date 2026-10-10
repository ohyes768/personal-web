# 宏观经济页按 Tab 拆分数据 API

## Goal

后端按 Tab 提供独立数据查询接口；前端切换 Tab 时拉取该 Tab 的全历史数据并缓存，切换时间周期仅在本地切片，无需重新请求。

## Background

当前 `GET /api/data?start_date=2000-01-01` 一次返回全部序列（美债/德债/商品/股指等），前端进页即拉 5–10MB 大包。用户希望职责更清晰：每个 Tab 对应自己的数据域，切 Tab 才加载，切时间周期秒开。

## Requirements

### 功能需求

- R1 新增 `GET /api/data/{tab}`，`tab` 与前端 `TabType` 对齐（不含 `macro-signal`，该 Tab 已有独立接口）。
- R2 各 Tab 只加载并返回该 Tab 所需字段；默认时间范围为 `historical_start_date`（2000-01-01）至今日，支持可选 `start_date` / `end_date` 覆盖。
- R3 保留原 `GET /api/data` 行为不变（向后兼容）。
- R4 前端：切换 Tab 时请求对应 `/api/macro/data/{tab}`，按 Tab 内存缓存；`timeRange` 变化仅本地 `useFilteredEconomicData` 切片。
- R5 手动刷新（`refreshKey++`）清空当前 Tab 缓存并重新拉取。

### Tab 数据域

| tab | 后端加载段 |
|-----|-----------|
| treasury-exchange | us_treasuries, exchange_rates, china_bond(10y) |
| bonds | us_treasuries(日期轴), eu_bonds, jp_bonds |
| liquidity-risk | us_treasuries(日期轴), vix, tga, hibor |
| rates | us_treasuries(日期轴), ted_spread, china_bond |
| comparison | 全部段 |
| commodities | us_treasuries(日期轴), commodities |
| stock-indices | us_treasuries(日期轴), indices |

### 非功能

- C1 `query_data_by_tab` 复用现有 `_query_data_impl` 逻辑，通过 `sections` 跳过无关 CSV 读取。
- C2 缓存 key 含 `(version, tab, start, end)`，与现有 5min TTL 一致。

## Acceptance Criteria

- [ ] AC1 `GET /api/data/treasury-exchange` 返回 200，含 dates/us_treasuries/exchange_rates/china_bond，不含 commodities/indices。
- [ ] AC2 `GET /api/data/bonds` 返回 eu/jp treasuries，不含 exchange_rates。
- [ ] AC3 `GET /api/data/invalid` 返回 400。
- [ ] AC4 原 `GET /api/data` 仍返回全量字段。
- [ ] AC5 前端切 Tab 触发对应 API；同 Tab 再切时间周期无新网络请求。
- [ ] AC6 刷新按钮后当前 Tab 数据更新。

## Out of Scope

- macro-signal Tab（已有 `/signal`、`/months`）。
- 按 Tab 独立时间周期状态（仍用页面级 `timeRange`）。
