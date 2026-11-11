# Frontend guidelines

## Pre-development checklist

- Every app's main page must expose a visible `← 返回首页` link near its header,
  pointing to the project-wide root `/`. Use a native `<a href="/">`, not Next Link
  or router navigation that can prepend the app's basePath. Preserve keyboard focus
  visibility and ensure the entry remains available on mobile layouts.
- For apps/dividend fundamental-report reading work (the `/quality-reader` page, the main-page entry, or the shared report body), read [基本面资料阅读页前端契约](./dividend-quality-reader.md); it fixes the reading-collection order, the `code`-as-identity URL rule, and the `/dividend` prefix handling.
- For apps/dividend 「全部」页股票搜索（搜索条、`/api/dividend/stocks?search=`、只看收藏时收窄到收藏 codes），read [股息率「全部」页股票搜索契约](../backend/dividend-select/backend/stock-search-contract.md).
- For apps/skill-manager UI work, read [skill-manager control language](./skill-manager-ui.md); use `lib/ui.ts` constants, never hand-rolled button/input classes.
- For apps/service-manager（NAS 服务管理台，`/services`）, read [service-manager frontend contract](../apps/service-manager/frontend/index.md); 状态展示铁律（五个维度不许合并、未配置 health 不许显示「健康」、端口范围提示）与 SafeLink/真实 URL 约束都在那里。
- For apps/macro time-series charts, read [ECharts contracts](./macro-echarts.md).
- For apps/index-trends candlestick+channel charts, read [index-trends ECharts contracts](./index-trends-echarts.md); the valuation display contract lives in the same file.
- For apps/fund-select 夏普榜单页（`/funds/sharpe-board`）或其图表/展示筛选，read [fund-sharpe-board 前端契约](./fund-sharpe-board.md); 后端周榜/聚合契约在同包 backend contracts §13.
- For backend/index-trends weekly pipeline or lixinger valuation, read [index-trends backend spec](../backend/index-trends/backend/index.md) (weekly-pipeline.md, valuation-contract.md).
- For apps/housing-map housing-type switching, project points or nearby comparison, read [New-house projects on the shared map](../backend/housing-map/backend/newhouse-map.md); market classification, distance and price text live in `lib/market-map.ts`.
- Preserve API units, null observations, display transformations, independent calendars, and Tab lazy loading.
- Read shared code-reuse guidance before adding wrappers or chart utilities.

## Quality check
- Run apps/macro TypeScript check and production build.
- Run the chart option tests described in macro-echarts.md.
- Verify actual slider input, reset, hidden-Tab switching, legend toggles, all comparison modes, and 375px/1440px layouts.
- Most apps still have no ESLint configuration, so `next lint` (deprecated in Next 15, removed in Next 16) prompts interactively and cannot run in a script or CI — report this limitation explicitly. apps/dividend is the exception since 2026-11-04: it has `apps/dividend/eslint.config.mjs` (flat config, `FlatCompat` bridge because `eslint-config-next@15` only ships eslintrc-style configs) and its `lint` script is `eslint`.
- Keep [historical Plotly contracts](./macro-plotly.md) for archived tasks, not as current rendering instructions.
- For apps/dividend: run `node --experimental-strip-types --test src/lib/quality-reader.test.ts` and `npx playwright test` (full suite). The screening table's compact rating cell renders dimension labels inline (`业务模式4护城河4…`, unrated dimensions show `—`) since upstream change `66b268af`; the Skill version moved into the button `title` tooltip since `3cf5836e` — assert against that shape, not the old `4/4/3/3/5（v4.3.0）` string.
- For apps/dividend 股票搜索改动：另跑 `node --experimental-strip-types --test src/lib/stock-search.test.ts` 与 `npx playwright test e2e/stock-search.spec.ts`（搜索命中阈值外股票、无匹配空状态、清空恢复、只看收藏带 codes）。
