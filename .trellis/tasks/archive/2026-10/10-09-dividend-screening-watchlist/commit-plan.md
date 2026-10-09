# 提交计划（用户已确认）

1. `feat(dividend): 新增选股关注筛选与批量收藏`

仅包含本次实现、测试、规范和规划文件：

- `apps/dividend/playwright.config.ts`
- `apps/dividend/tsconfig.json`
- `apps/dividend/src/app/page.tsx`
- `apps/dividend/src/components/ScreeningTab.tsx`
- `apps/dividend/src/lib/api.ts`
- `apps/dividend/src/lib/types.ts`
- `apps/dividend/src/lib/screening.ts`
- `apps/dividend/e2e/screening.spec.ts`
- `backend/dividend-select/src/api/models.py`
- `backend/dividend-select/src/api/routes.py`
- `backend/dividend-select/src/data/financial_fetcher.py`
- `backend/dividend-select/src/services/favorites_service.py`
- `backend/dividend-select/src/services/shareholder_financial_reader.py`
- `backend/dividend-select/src/services/screening_service.py`
- `backend/dividend-select/tests/test_financial_fetcher.py`
- `backend/dividend-select/tests/test_screening_service.py`
- `backend/dividend-select/tests/test_favorites_batch.py`
- `backend/dividend-select/tests/test_screening_financial_status.py`
- `.trellis/spec/backend/dividend-select/backend/index.md`
- `.trellis/spec/backend/dividend-select/backend/screening-watchlist-contract.md`
- `.trellis/tasks/10-09-dividend-screening-watchlist/implement.md`
- `.trellis/tasks/10-09-dividend-screening-watchlist/prd.md`
- `.trellis/tasks/10-09-dividend-screening-watchlist/task.json`
- `.trellis/tasks/10-09-dividend-screening-watchlist/implement.jsonl`
- `.trellis/tasks/10-09-dividend-screening-watchlist/check.jsonl`
- `.trellis/tasks/10-09-dividend-screening-watchlist/design.md`
- `.trellis/tasks/10-09-dividend-screening-watchlist/research/current-state.md`
- `.trellis/tasks/10-09-dividend-screening-watchlist/commit-plan.md`

## 其他工作区改动

以下不是本次会话修改，不纳入提交：

- `.trellis/spec/frontend/macro-plotly.md`
- `.trellis/tasks/08-29-macro-echarts-refactor/check.jsonl`
- `.trellis/tasks/08-29-macro-echarts-refactor/implement.jsonl`
- `.trellis/tasks/08-29-macro-echarts-refactor/prd.md`
- `.trellis/tasks/08-29-macro-echarts-refactor/task.json`
- `apps/macro/package.json`
- `apps/macro/pnpm-lock.yaml`
- `apps/macro/src/app/modules/economic/components/CommodityChart.tsx`
- `apps/macro/src/app/modules/economic/components/ComparisonChart.tsx`
- `apps/macro/src/app/modules/economic/components/EconomicChart.tsx`
- `apps/macro/src/app/modules/economic/components/HsgtFundFlowChart.tsx`
- `apps/macro/src/app/modules/economic/components/LinkedSubplots.tsx`
- `apps/macro/src/app/modules/economic/components/LiquidityChart.tsx`
- `apps/macro/src/app/modules/economic/components/MacroPlot.tsx`
- `apps/macro/src/app/modules/economic/components/MarketSentimentChart.tsx`
- `apps/macro/src/app/modules/economic/components/RatesChart.tsx`
- `apps/macro/src/app/modules/economic/components/StockIndexChart.tsx`
- `apps/macro/src/app/modules/economic/page.tsx`
- `apps/macro/src/lib/hooks/usePlotlyAutoResize.ts`
- `apps/macro/src/lib/modules/comparison/indicators.ts`
- `apps/macro/src/lib/modules/comparison/normalize.ts`
- `apps/macro/src/lib/modules/comparison/viewMode.ts`
- `apps/macro/src/lib/types/economic.ts`
- `apps/macro/src/lib/utils/chartConfig.ts`
- `apps/macro/src/lib/utils/plotlyTheme.ts`
- `apps/macro/src/types/shim-plotly-dist.d.ts`
- `apps/macro/src/types/shim-react-plotly.d.ts`
- `.pnpm-store/`
- `.trellis/spec/frontend/index.md`
- `.trellis/spec/frontend/macro-echarts.md`
- `.trellis/tasks/08-29-macro-echarts-refactor/commit-plan.md`
- `.trellis/tasks/08-29-macro-echarts-refactor/design.md`
- `.trellis/tasks/08-29-macro-echarts-refactor/implement.md`
- `.trellis/tasks/08-29-macro-echarts-refactor/verification.md`
- `.trellis/tasks/10-09-macro-chart-analysis/`
- `apps/macro/src/app/modules/economic/components/MacroEChart.tsx`
- `apps/macro/src/lib/utils/chartTheme.ts`
- `apps/macro/src/lib/utils/echartsOptions.test.ts`
- `apps/macro/src/lib/utils/echartsOptions.ts`

用户已于 2026-10-10 确认执行上述单次工作提交；不推送。任务归档/会话记录按 Trellis 后续流程另行处理。
