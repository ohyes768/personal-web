# Frontend guidelines

## Pre-development checklist
- For apps/macro time-series charts, read [ECharts contracts](./macro-echarts.md).
- Preserve API units, null observations, display transformations, independent calendars, and Tab lazy loading.
- Read shared code-reuse guidance before adding wrappers or chart utilities.

## Quality check
- Run apps/macro TypeScript check and production build.
- Run the chart option tests described in macro-echarts.md.
- Verify actual slider input, reset, hidden-Tab switching, legend toggles, all comparison modes, and 375px/1440px layouts.
- next lint currently needs initial ESLint configuration; report this limitation explicitly.
- Keep [historical Plotly contracts](./macro-plotly.md) for archived tasks, not as current rendering instructions.
