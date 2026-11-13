# apps/fund-select 夏普走势页前端契约（11-13-fund-sharpe-trend）

> 后端口径/API/KPI 定义见 [backend contracts §17](../backend/fund-select/backend/contracts.md)。
> 图表基建复用 [fund-sharpe-board.md](./fund-sharpe-board.md) 的
> `SharpeChart.tsx` + `lib/sharpe-chart.ts`，不重复造图。

## 1. 页面定位

`/funds/sharpe-trend?code=xxxxxx`，导航第七 Tab（`FundsNavTab` 已加
`'sharpe-trend'`）。与夏普榜单的关系：

| 页面 | 回答 | 数据 |
|---|---|---|
| 股基两 tab 列表 | 现在谁好？ | 每周刷新的一帧快照 |
| 夏普榜单 | 谁一直好？（横向 N 只） | 每周冻结的周观测（≥0.8 才记录，有幸存者偏差） |
| **夏普走势** | **这一只稳不稳？** | 现算完整滚动曲线（跌破 0.8 也看得见） |

页面自行组装头部（返回首页 `<a href="/">` + h1 + `FundsNavigation`），
**不套 `FundsHeader`**（它没有 `sharpe-trend` 的 active 值）。

## 2. URL 协议

- `?code=xxxxxx` — 6 位数字，`FUND_CODE_PATTERN = /^\d{6}$/`，非法回退 null
  显示引导态（不报错、不造曲线）。
- `?range=all|3y|1y` — 默认 `all`，默认值**不写 URL**。
- 区间切换 `trendRangeHref(code, range)` 保留 code，只改 range；
  用 `Link` 客户端导航，不整页刷新（canvas/dataZoom 状态保留）。
- `sharpeTrendHref(code, range?)` 生成跨页跳转链接，**相对 basePath**：
  `/sharpe-trend?code=...`，写 `/funds/...` 会产出 `/funds/funds/...` 404。

## 3. 数据请求

- `fetchSharpeTrend(code, range, signal)` 走**全路径**
  `/funds/api/funds/sharpe-trend/{code}`；后端 404/502 抛结构化错误，
  前端显示「加载失败：...」+ 重试按钮。
- `useEffect` 依赖 `[code, range, reloadTick]`，每次都用
  `AbortController` 中止旧请求（防旧响应覆盖新状态）。
- 正常空态 `diagnostics.insufficient_history` → 「历史不足，无法计算滚动夏普」，
  **不是错误**。
- 图表适配：`weeks = points.map(p => p.date)`，
  `series = [{code, name: data.name ?? code, values: points.map(p => p.sharpe)}]`
  直接喂 `SharpeChart`（单 series，`minLatestSharpe=0.8`）。

## 4. KPI 组件

`components/sharpe-trend/SharpeTrendStats.tsx`（`SharpeTrendStatsPanel`）：
六格 `grid-cols-2 sm:grid-cols-3 lg:grid-cols-6`，另有次级一行展示
`longest_below` / `trend_12w` / `rf_basis` / `algorithm_version`。

达标语义 ≥0.8 含等号；`current` 用绿色（≥阈值）/ 红色（<阈值）/ 灰（na）；
`formatSharpe` 两位小数，`formatRatio` 百分比，`formatSlope` 带符号。
**口径说明必须显示**：`rf_basis="zero"` 时写「按 0（利率表为空）」，不静默。

## 5. 三处入口（第一版只支持股基）

1. `FundTable` 加 `trendEnabled?: boolean`，仅 `stock/page.tsx` 与
   `discovery-stock/page.tsx` 传 true。代码列 Link 的 `onClick` 必须
   `e.stopPropagation()`，否则同时触发 `<tr onClick>` 打开详情抽屉。
2. `RiskMetricsGrid` 加 `trendHref?: string`，**只有**夏普卡片包 `<Link>`；
   `DetailHero` 传 `/sharpe-trend?code=${fund.code}`。
   `RowDetailDrawerBond`（债基）不使用 `DetailHero`，故无此入口。
   ⚠ 用显式 `isSharpeLink ? <Link .../> : <div>...` 分支，
   别用动态 `const Wrapper = isLink ? Link : 'div'` —— TS 会把 Link 的
   必填 `href` 强加给 div 分支报 TS2322。
3. `SharpeBoardTable` 代码列改成 Link（保留下方 10px「详情」小按钮开抽屉），
   行点击是「聚焦」，Link 同样需 `stopPropagation`。

债基两 tab 不传 `trendEnabled`（默认 false）→ 代码纯文本，UI 零变化。

## 6. 常见坑

- **basePath 双前缀**：见 §2。
- **Tailwind v4 任意值类缓存**：图容器 `h-[420px] w-full` 若未渲染，
  删 `.next` 重启 dev；`SharpeChart` 有零尺寸守卫 + ResizeObserver。
- **复用榜单图表**：`SharpeChart` 的 `onLegendChange` 单基金无意义，
  传空函数即可；`hiddenCodes` 传空 Set。
- **无 ESLint 配置**：`next lint` 不能非交互运行，如实报告，不得声称通过。

## 7. Tests Required

```bash
# cwd apps/fund-select
node --experimental-strip-types --test src/lib/sharpe-trend.test.ts \
  src/lib/sharpe-board.test.ts src/lib/sharpe-chart.test.ts
pnpm exec tsc --noEmit
```
浏览器 E2E（人工）：无 code 引导态 → 输入 002910 跳转 → 区间切 1y
点数 453→52 且不整页刷新 → 股基列表/抽屉夏普卡/榜单行三处跳转 →
债基代码不可点。
