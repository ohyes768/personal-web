# 行情价与M120解耦修复挡位监控空窗

## 背景 / 根因

「挡位监控」tab 在 M120 数据缺失时整页空白(tab 计数仍显示 N，但点进去无内容、也无空状态提示)。

根因链：
1. 前端挡位监控 bar 的现价 `currentPrice` 取自 `useTechnicalData`，其唯一数据源是 `GET /api/dividend/m120`。
2. 后端 `m120_service.read_m120_with_deviation()` **以 M120 CSV 为主表** join 实时价格；`if not M120_CSV_FILE.exists(): return {}` —— M120 文件缺失时整表返回空，**实时价格 CSV 的数据被一起埋没**。
3. 实时价格(close/realtime/pe/pb)与 M120 均线本就是**两套独立数据、两个独立 CSV、两个独立刷新任务**(日度 vs 周度)。挡位监控 bar 只需现价 + PE/PB + yield_ttm，**语义上与 M120 均线无关**，却被 M120 接口绑架。

## Goal

让挡位监控的现价取数与 M120 彻底解耦：M120 数据缺失不再导致挡位监控空窗，只要实时价格 CSV 有数据，挡位 bar 正常渲染。

## Requirements

### 后端 (backend/dividend-select)
- 新增 `read_prices_only()`：只读实时价格 CSV，不以 M120 为主表，返回 `{code: {close, realtime, pe, pb}}`。
- 新增 `GET /api/dividend/prices?codes=<csv>` 接口：返回 `{total, items: [{code, close, realtime, pe, pb, yield_ttm}], last_updated}`。
  - `yield_ttm` 复用现有算法(近5年分红详情 + `DividendCalculator.get_ttm_dividend` / realtime)。
  - `codes` 为空时返回实时价格 CSV 中全部股票。
- **不改动** `GET /api/dividend/m120` 与 `read_m120_with_deviation()` 的对外行为(其他消费者众多，避免回归)。

### 前端 (apps/dividend)
- 新增现价取数能力(api.ts `getPrices` + types + `useRealtimePrices` hook)。
- 挡位监控 tab 渲染(`page.tsx` 1068-1087)的 `currentPrice/pe/pb/yield_ttm` 改从现价 hook 取，不再读 `technicalData`。
- 其余消费 `technicalData` 的地方(DivididendTable、对比、报告、CSV 导出)**不动**。

## Acceptance Criteria

- [ ] **核心**：清空/缺失 M120 CSV 后，挡位监控 tab 仍能正常渲染 bar(只要实时价格 CSV 有数据)。
- [ ] `GET /api/dividend/prices` 在实时价格 CSV 存在时返回数据；M120 CSV 缺失不影响其返回。
- [ ] `GET /api/dividend/m120` 行为不变(现有 M120/偏离度展示不受影响)。
- [ ] 挡位监控 bar 的现价/PE/PB/TTM 展示与改造前一致(数据源换成现价接口，值不变)。
- [ ] 后端 `pytest` 既有用例无回归；新增 `read_prices_only` 单测。
- [ ] 前端 `pnpm lint` + `pnpm build` 通过。

## 非目标 (Out of Scope)

- 不重构 `read_m120_with_deviation` 的 join 语义(影响面大)。
- 不拆分 `/api/dividend/m120` 的响应字段。
- 不处理「实时价格 CSV 也不存在」的极端空窗(属另一问题，implement 中仅备注降级)。
- 不改其他 tab(全部/收藏)的取数。
