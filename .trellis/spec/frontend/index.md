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
- For apps/dividend 收藏跟踪 Tab（四挡位估值的行状态、查看报告 / 应用两个动作、确认卡），read [四挡位估值契约](../backend/dividend-select/backend/valuation-contract.md)；行内「应用」写生效挡位，「查看报告」只读，两者不合并。
- For apps/dividend 弹窗（`src/components/shared-ui/Modal.tsx`）：**正文不要再套 `max-h-*` + `overflow-y-auto` 容器**。Modal 内容区（`flex-1 overflow-y-auto p-6`）已是唯一竖向滚动区，嵌套会渲染出两条竖向滚动条（长报告尤其明显）。底部操作区用 Modal 的 `footer` 插槽钉在弹框底部，正文滚动时按钮始终可见；只有「列表本身需要独立滚动」这种局部场景（如某块名单）才保留内层横滑/滚动容器。
- For apps/macro time-series charts, read [ECharts contracts](./macro-echarts.md).
- For apps/index-trends candlestick+channel charts, read [index-trends ECharts contracts](./index-trends-echarts.md); the valuation display contract lives in the same file.
- For apps/fund-select 夏普榜单页（`/funds/sharpe-board`）或其图表/展示筛选，read [fund-sharpe-board 前端契约](./fund-sharpe-board.md); 后端周榜/聚合契约在同包 backend contracts §13.
- For apps/fund-select 基金代码搜索（`?search_code=`、`buildSearchHref`、搜索 chip），read [fund-select backend contracts](../backend/fund-select/backend/contracts.md) §20；核心约束：搜索态与筛选并存、落点 URL 必须走 `buildSearchHref`（直接 push 后端 path 会丢筛选）、搜索态不计入 `activeCount`。
- For apps/fund-select 夏普走势页（`/funds/sharpe-trend`）或其 KPI/入口，read [fund-sharpe-trend 前端契约](./fund-sharpe-trend.md); 后端现算口径契约在 backend contracts §17.
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
- For apps/fund-select 代码搜索改动：另跑 `node --experimental-strip-types --test src/lib/search-code.test.ts`（归一化、只发 `code=`、`buildSearchHref` 保留筛选）与后端 `tests/test_code_search.py`（阈值被忽略、清盘基金仍返回）。
- For apps/dividend 四挡位估值改动：另跑 `node --experimental-strip-types --test src/lib/valuation.test.ts`（现价落在哪一区 / 会不会触发提醒，判定口径必须与后端 `AlertService._find_hit_level` 一致）。
- For apps/dividend 股票搜索改动：另跑 `node --experimental-strip-types --test src/lib/stock-search.test.ts` 与 `npx playwright test e2e/stock-search.spec.ts`（搜索命中阈值外股票、无匹配空状态、清空恢复、只看收藏带 codes）。
