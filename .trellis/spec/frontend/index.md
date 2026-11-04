# Frontend guidelines

## Pre-development checklist
- For apps/dividend fundamental-report reading work (the `/quality-reader` page, the main-page entry, or the shared report body), read [基本面资料阅读页前端契约](./dividend-quality-reader.md); it fixes the reading-collection order, the `code`-as-identity URL rule, and the `/dividend` prefix handling.
- For apps/skill-manager UI work, read [skill-manager control language](./skill-manager-ui.md); use `lib/ui.ts` constants, never hand-rolled button/input classes.
- For apps/macro time-series charts, read [ECharts contracts](./macro-echarts.md).
- For apps/index-trends candlestick+channel charts, read [index-trends ECharts contracts](./index-trends-echarts.md); the valuation display contract lives in the same file.
- For backend/index-trends weekly pipeline or lixinger valuation, read [index-trends backend spec](../backend/index-trends/backend/index.md) (weekly-pipeline.md, valuation-contract.md).
- For apps/housing-map housing-type switching, project points or nearby comparison, read [New-house projects on the shared map](../backend/housing-map/backend/newhouse-map.md); market classification, distance and price text live in `lib/market-map.ts`.
- Preserve API units, null observations, display transformations, independent calendars, and Tab lazy loading.
- Read shared code-reuse guidance before adding wrappers or chart utilities.

## Quality check
- Run apps/macro TypeScript check and production build.
- Run the chart option tests described in macro-echarts.md.
- Verify actual slider input, reset, hidden-Tab switching, legend toggles, all comparison modes, and 375px/1440px layouts.
- next lint currently needs initial ESLint configuration; report this limitation explicitly.
- Keep [historical Plotly contracts](./macro-plotly.md) for archived tasks, not as current rendering instructions.
- For apps/dividend: run `node --experimental-strip-types --test src/lib/quality-reader.test.ts` and `npx playwright test e2e/quality-reader.spec.ts e2e/screening.spec.ts`. Three `screening.spec.ts` cases (`compact rating preserves partial scores…`, `skill version display: …`) fail because the 2026-11-02 upstream UI change `66b268af` was not mirrored in their assertions — treat them as a stale baseline, not a new regression.
