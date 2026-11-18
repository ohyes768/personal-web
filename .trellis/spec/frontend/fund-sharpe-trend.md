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

> **11-16 就地弹框**：股基列表点「夏普」列数值、详情抽屉点夏普卡片，改为**就地弹框**
> `components/sharpe-trend/SharpeTrendDialog.tsx`（不离开当前页）。弹框与独立 Tab 页共用
> `components/sharpe-trend/SharpeTrendBody.tsx`（区间切换 + 6 格稳定性 KPI + 滚动夏普曲线），
> 两边**样式一致**。独立 Tab 页保留（导航第七 Tab + `?code=` 直达 + 代码输入框），方便手动输入 / 分享链接。
> 弹框头部另有「独立页」链接（`sharpeTrendHref(code, range)`）跳过去。
> 取数抽成 `lib/useSharpeTrend.ts`（AbortController 中止旧请求），页与弹框共用。

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

## 5. 入口（11-16 就地弹框版，只支持股基）

1. `FundTable`：
   - `trendEnabled?: boolean` → 代码列 Link 跳**独立页**（`sharpeTrendHref`），
     `onClick` 必须 `e.stopPropagation()`（否则同时触发 `<tr onClick>` 开详情抽屉）。
   - `onTrendOpen?: (code) => void` → **「夏普」列数值**变按钮，点它弹
     `SharpeTrendDialog`（就地看走势，不离开列表）。同样 `stopPropagation`。
   - `stock/page.tsx` 同时传两者；`SharpeBoardTable` / 债基 tab 不传 → 零变化。
2. `RiskMetricsGrid` 加 `onTrendOpen?: () => void`，**只有**夏普卡片变按钮走弹框；
   `trendHref?: string` 保留为不传 `onTrendOpen` 时的整页跳转兜底。
   `DetailHero → RowDetailDrawer → stock/page.tsx` 一路把 `onTrendOpen` 透传下来，
   `stock/page.tsx` 用同一个 `trendCode` state 弹同一个 `SharpeTrendDialog`。
   ⚠ `isSharpeLink ? (onTrendOpen ? <button/> : <Link/>) : <div/>` 显式分支，
   别用动态 `const Wrapper = isLink ? Link : 'div'` —— TS 会把 Link 的必填 `href`
   强加给 div 分支报 TS2322。
3. `SharpeBoardTable` 代码列仍是 Link 跳独立页（保留下方「详情」小按钮开抽屉），
   行点击「聚焦」需 `stopPropagation`。

弹框与详情页的层级：`SharpeTrendDialog` 用 `z-[60]` 盖在 `RowDetailDrawer`（`z-50`）之上；
**Escape 必须在 capture 阶段 `stopPropagation`**，否则详情抽屉的 document 监听也会触发，
两层一起关 + 两处 `body.overflow` 恢复互相打架。弹框内切区间用 `setRange`（不改 URL），
独立页切区间用 `router.push`（同步 `?range=`），二者共用 `useSharpeTrend(code, range)`。

债基两 tab 不传 `trendEnabled` / `onTrendOpen` → 代码、夏普均纯文本，UI 零变化。

## 6. 常见坑

- **basePath 双前缀**：见 §2。
- **Tailwind v4 任意值类缓存**：图容器 `h-[420px] w-full` 若未渲染，
  删 `.next` 重启 dev；`SharpeChart` 有零尺寸守卫 + ResizeObserver。
- **复用榜单图表**：`SharpeChart` 的 `onLegendChange` 单基金无意义，
  传空函数即可；`hiddenCodes` 传空 Set。
- **弹框开在抽屉之上**：Escape 用 capture + `stopPropagation`（见 §5）；
  遮罩点击 / × 只关弹框，不动下层抽屉。
- **无 ESLint 配置**：`next lint` 不能非交互运行，如实报告，不得声称通过。

## 7. Tests Required

```bash
# cwd apps/fund-select
node --experimental-strip-types --test src/lib/sharpe-trend.test.ts \
  src/lib/sharpe-board.test.ts src/lib/sharpe-chart.test.ts
pnpm exec tsc --noEmit
```
浏览器 E2E（人工）：无 code 引导态 → 输入 002910 跳转 → 区间切 1y
点数 453→52 且不整页刷新 → 股基列表「夏普」数值弹框、抽屉夏普卡片弹框、
代码列 / 榜单行跳独立页 → 弹框内切区间不改 URL、Escape 只关弹框保留抽屉 →
债基代码与夏普均不可点。
