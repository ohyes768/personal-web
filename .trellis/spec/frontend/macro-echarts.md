# Macro ECharts contracts

## Scope / Trigger
All time-series charts in apps/macro now use ECharts 6 via MacroEChart. Read this before modifying rendering, date ranges, axes, tooltips, or future analysis context. Plotly's old spec is historical.

## Signatures
- buildLineTrace(meta, dates, values, { details? }) → ChartSeries | null.
- buildEChartsOption(lines, layout, range, narrow) → EChartsOption.
- MacroEChart({ data, layout, chartId, range?, onRangeChange?, onContextChange? }).
- LinkedSubplots({ subplots, chartId, onContextChange? }).
- Every business chart exposes optional onContextChange; no model integration is included.

## Contracts
- ChartSeries.id is a stable business key independent of its translated name. ChartContext carries chartId, complete series IDs/units/display transformations, and visible dates. Legend visibility does not alter analysis membership.
- Dates are ISO day strings. Join different source axes by date; leave absent observations null. Never connect gaps. API-side fill behavior is outside the renderer.
- DateRange is [start, end] or null for full range. LinkedSubplots owns controlled range; MacroEChart owns range when uncontrolled. Data changes reset zoom.
- ECharts category indices are local to each date array. Convert zoom to dates before sharing. Round category percentages to the nearest observation; do not repeatedly ceil/floor and drift the bounds.
- Programmatic setOption is silent and receives fresh options. It must not emit user range changes or create feedback loops.
- Independent instances preserve independent legends and axes. Register only LineChart, Grid, Tooltip, Legend, DataZoom, MarkLine and CanvasRenderer via echarts/core.
- Keep normalization/statistics outside the renderer. Tooltips use typed detail fields, not HTML templates. Relative FX and normalized comparisons retain original values. TGA display scaling is declared with transform=scaled and scaleFactor.
- React owns wrapping legend buttons and full axis titles. Date endpoint labels align inward; narrow layouts must not crop labels.
- Empty series must not initialize an ECharts instance or create orphan dataZoom components; ECharts otherwise can throw during render and later disposal.
- Hidden tabs initialize only at nonzero dimensions. ResizeObserver handles visibility/width changes; dispose instances and observers on cleanup.

## Validation & Error Matrix
| Condition | Expected behavior |
|---|---|
| All-null/non-finite series | Excluded; all-empty chart shows emptyMessage |
| Sparse series | Null gaps and markers for fewer than 8 valid points |
| Hidden container | Defer initialization, redraw at nonzero size |
| Render failure | Log error and show retry-by-refresh message |
| Reset button / double click | Shared range=null; current dataset full range |
| Changed range / chart identity | Context callback reports explicit dates and chartId |
| All legends hidden | Existing curves stay in analysis context |

## Good / Base / Bad Cases
Good: China10y and spread use y3/y4 descriptors but map to local ECharts axis indices 0/1; zoom on one rates panel shares dates with the other two.
Base: Different source dates produce a union date axis with null placeholders.
Bad: Passing source indices across panels with different calendars selects the wrong dates.

## Tests Required
Compile src/lib/utils/echartsOptions.test.ts using local tsc with CommonJS output in a temporary directory, then node --test on the generated JS. Tests cover dual-axis mapping, gaps, non-finite values, short markers, date joins, zoom/reset, transformed tooltip details, and input immutability.
Run tsc --noEmit and next build; use actual browser input for slider dragging, reset, legend, hidden-tab switching, 375px/1440px sizes, and all four comparison modes. Stop the preview before rebuilding the same .next directory.

## Wrong vs Correct
Wrong: Send Plotly trace/layout objects to the new renderer, derive chart identity from Chinese labels, or let setOption trigger a new zoom callback.
Correct: Build typed ChartSeries/ChartLayout, use explicit stable IDs, and update options silently.

## Operational notes
The repository currently has no ESLint configuration; next lint requests interactive setup. Do not claim lint passed merely because the production build succeeds. Dependency installation and builds should not introduce unrelated pnpm workspace policy files.
