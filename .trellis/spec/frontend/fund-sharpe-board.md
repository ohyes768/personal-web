# fund-select 夏普榜单页前端契约（2026-11-05，任务 11-04-fund-sharpe-weekly-board）

独立 Tab「夏普榜单」：`src/app/sharpe-board/page.tsx` → URL `/funds/sharpe-board`。只读页面（数据全部来自 `GET /api/funds/sharpe-board`，后端契约见 `../backend/fund-select/backend/contracts.md` §13），页面内所有筛选都是**展示筛选**，绝不触发采集；采集入口只有复用的 `SchedulerDialog`（齿轮）。

## 1. 路由与请求

- 五 Tab 公共导航是 `src/components/FundsNavigation.tsx`，`FundsHeader` 与新页共用；`FundsTab`/`exportKind` 仍只代表四个采集来源，**不得**把夏普榜单伪造进刷新来源。旧四页除导航组件替换外零行为变化。
- basePath 契约同 contracts §4：`<Link>` 用相对路径（`/sharpe-board`）；`fetch` 必须写全路径 `/funds/api/funds/sharpe-board`；URL 同步只拼 `?qs`。
- `src/lib/sharpe-board.ts` 独立持有 TS DTO（对齐后端 6 个 `SharpeBoard*` DTO）、URL 参数 parse/serialize（**默认值省略不写**：source=discovery-stock、range=all、page=1、min_listed_pct=60 都不落 URL）、`fetchSharpeBoard`。**source 切换必须 AbortController 中止旧请求**，否则旧来源响应会覆盖新来源状态。
- 后端 DTO 加字段时三处同步（同 §3a 三处清单）：`src/api/models.py` ↔ `src/lib/sharpe-board.ts` ↔ 页面消费；枚举值（source/range/status）两端字面一致。

## 2. ECharts 图表

- `echarts ^6` 装在本 app（pnpm，锁文件一起改）；仅新页 `dynamic(() => import(...), { ssr: false })`；不跨应用 import。`src/lib/sharpe-chart.ts` 是**零依赖纯 option 构造**（不 import echarts/React），node:test 直跑；`SharpeChart.tsx` 只管实例生命周期（init/ResizeObserver/dispose、隐藏或零尺寸容器不 init）。
- 图合同（option 测试锁定）：`connectNulls:false`、`smooth:false`、缺席周断线留空、单点可见——孤立点用 `isolatedPoints` 标记后 `showSymbol:true` + `symbolSize` 回调（孤立点 4px，连续点 0）。**不要**用 `showSymbol:false`（孤立单点完全不渲染）也不要全量 symbol（300 线铺满画布）。纵轴不强制从零、夏普下限参考线、series=全部命中基金（不随列表分页截断）。
- **翻页/筛选重拉不重建图**：图表 effect 依赖 `dataSignature`（`JSON.stringify([weeks, series.map(s => [s.code, s.values])])`）而非数组引用——翻页时 series 内容不变，实例存活，dataZoom/tooltip 状态保留；数据真变（source 切换/新周）签名变化照常重建。图例状态以 React 为单一真相源（`legendselectchanged` 回传父组件），隐藏集变化走 merge `setOption({legend:{selected}})` 不重置缩放。
- 列表行「聚焦」按钮联动图例高亮，「恢复全部」清空 hidden 与聚焦。

## 3. 状态与文案

五种状态必须区分，不能都渲染成「暂无数据」：首次无数据（库空）、请求失败（可重试）、成功空榜 vs 采集失败（StatusBar：失败红条带 errors、样本未更新灰条、stale 提示「旧榜日期不冒充本周」）、展示筛选无匹配（带「清除展示筛选」）、时间范围内无点（列表保留，图不造点）。字段文案是「最近上榜夏普」，不得写成「当前夏普」；「最近连续周数」含义是最近一段连续在榜（**§9 起：数据缺口周不中断，真实缺席才中断**）。

## 4. 布局

- 1440px：筛选一行排布；390px：筛选 flex-wrap 换行、表格容器局部横向滚动（**不是**整页滚动），整页 `document.documentElement.scrollWidth <= 390`。
- 图容器固定高 `h-[420px] w-full`；零尺寸时守卫拒绝 init，容器恢复尺寸由 ResizeObserver 触发渲染。

## 5. 常见坑

- **Tailwind v4 任意值类不生效 → 图不出来**：dev 期间新组件的 `h-[420px]` 可能不在编译产物里（`.next` 陈旧缓存，同 housing-map 的 CSS 陈旧坑），表现为图容器 clientHeight=0、「守卫不 init」静默不出图。处置：删 `.next` 重启 dev server，别反复 reload。
- **浏览器面板零视口**：窗口最小化时 `window.innerWidth===0`，图表守卫不 init 是**正确行为**；无头验证先 `preview_resize` 模拟视口，截图需窗口前台。
- `npm run build` 在 standalone 拷贝阶段报 EPERM symlink（Windows 权限）：如实记录，用临时移除 `output:'standalone'` 的完整 build 作替代证据，验完还原。
- 本 app 无 ESLint 交互配置，`next lint` 不能非交互运行——不得声称 lint 通过。

## 6. Tests Required

```bash
# cwd apps/fund-select；纯逻辑测试不 import React/echarts，相对 import 带 .ts 后缀
node --experimental-strip-types --test src/lib/sharpe-board.test.ts src/lib/sharpe-chart.test.ts
npx tsc --noEmit
npm run build   # standalone EPERM 见 §5
```

- `sharpe-chart.test.ts`：固定断言 `option.series[0].data === [0.95, null, 1.05]`、`connectNulls===false`、`smooth===false`；孤立点 symbolSize>0、连续段 0；下限参考线存在。
- `sharpe-board.test.ts`：URL parse/serialize 默认值省略、AbortController 接线、五状态分类函数。
- 浏览器（改动后必测）：1440/390 无横溢出、断线与单点、翻页不重置图（canvas 同节点）、range 只裁图统计不变、来源快速切换。

## 7. v2 规则与 52 周窗口（11-13-sharpe-board-v2-rules，2026-11-13）

后端契约见 [backend §18](../backend/fund-select/backend/contracts.md)（三道门、peer 冻结、
52 周聚合、DTO 同步）。本节只记前端专属部分。

### 7.1 默认版本切 v2

`DEFAULT_SHARPE_FILTERS.profileVersion = 'v2'`（原 v1）。
`sharpeFiltersToQuery` 始终显式发 `profile_version`，URL 默认值省略不写。
`?profile_version=v1` 仍可访问历史版本（版本隔离）。

**测试注意**：`sharpeFiltersToSearch` 的「非默认值往返」用例原本用 v2 当非默认值，
v2 变默认后须改用 v1，否则失去对 `profile_version` 参数的往返覆盖。

### 7.2 `describeEntryFilters` 支持 v2 三道门

`SharpeBoardProfile.filters` 是 `Record<string, number | boolean>`，
新增键直接按数值渲染，v1 profile 无这些键时自动跳过：

- `min_ir` → `信息比率 IR ≥ 0.5`
- `min_sample_days` → `样本交易日 ≥ 700 天`
- `max_peer_pct` → `近三年同类排名前 20%`

### 7.3 表格新增两列（共 12 列）

| 列 | 渲染 | 备注 |
|---|---|---|
| 近52周在榜 | `listed_weeks` | 列名从「累计在榜周数」改，反映口径变更 |
| 近12周达标 | `formatNear12w(q, total)` → `n/m`；null → `—` | 达标数 < 半数时 `text-down` 预警 |
| 同类分位 | `formatPeerPct` → `前 14.2%`；null → `—` | `peer_as_of` 挂 `hover-tip` 显示数据日期 |

`min-w` 从 `560px` 提到 `760px`（12 列）；容器仍是**局部横向滚动**，
整页 `document.documentElement.scrollWidth <= 390` 不变。

### 7.4 「近 52 周」口径提示

`SharpeBoardProfileCard` 加一条独立说明行（蓝色徽标 + 说明），
与「规则版本 v2」相邻。理由：窗口截断后一年没上榜的基金 `listed_weeks=0`
会被硬门槛（窗口内曾在榜）筛掉，老基金「资历归零」容易让用户以为出 bug。
页面另两处过期文案同步：
- 无点空态：「列表仍按全历史统计」→「列表按近 52 周窗口统计」
- `RANGE_OPTIONS.all`：'全部' → '近一年(52周)'

### 7.5 常见坑（补充 §5）

- **`pnpm build` 与 `next dev` 共用 `.next`**：dev 期间 build 会清掉 dev 的 chunk，
  反之亦然。验证 build 产物时**另起一个端口的 `next start`**，不要复用 dev server。
- **容器里的 `next start` 用镜像内 `.next`**：本地 `pnpm build` 不会更新正在运行的
  `fund-select-frontend` 容器（nginx upstream 指向它）。端到端浏览器验证必须
  等部署；本地只能验到「build 产物含新代码 + 单测 + tsc」。
- **`next start` 对 `basePath` 的 `/funds/api/*` 不自动代理**：独立起的验证 server
  会因无后端代理返回 404，这是正常的，不代表前端代码有问题。

### 7.6 Tests Required（补充 §6）

```bash
node --experimental-strip-types --test src/lib/sharpe-board.test.ts   # 15 passed
npx tsc --noEmit
pnpm build
```

- 默认 v2、URL 往返（用 v1 当非默认值）
- `describeEntryFilters` 三道门全部渲染且 v1 五条件仍在
- 改 DTO 时三处同步：`src/api/models.py` ↔ `src/lib/sharpe-board.ts` ↔ 页面消费

## 8. v3 年度同类排名（11-14-sharpe-board-v3-yearly-peer，2026-11-14）

后端契约见 [backend §19](../backend/fund-select/backend/contracts.md)。

### 8.1 默认版本 v3

`DEFAULT_SHARPE_FILTERS.profileVersion = 'v3'`（原 v2）。
`?profile_version=v2` 仍可查（v2 的 `peer_pct` 滚动口径字段保留）。

### 8.2 「同类分位」列双口径渲染

```
peer_qualified_years !== null  →  `2/3 年`（hover 显示各年明细）
否则                            →  `前 14.2%`（v2 滚动口径，或 `-`）
```

- `peer_years` 是 `{"2023": 8.2, "2024": null, "2025": 12.5}` 形态，
  `null` 表示该年无数据，tooltip 显示「2023 无数据」而不是 0。
- `peer_window` 决定列出的年份顺序（后端给的是升序）。
- 两个口径的字段**不会同时有值**：v2 观测冻结 `peer_pct`，v3 冻结 `qualified_years`。

### 8.3 规则说明卡新增「同类排名口径」一行

`SharpeBoardProfileCard` 用 `filters.min_yearly_years` 判断当前是 v3 还是旧版：

- 有该字段 → 「最近 3 个完整年度（不含当年）中至少 N 年排前 X%；年度排名是历史固定值，因此可回溯。」
- 无 → 「沿用滚动口径（近三年分位）。」

`describeEntryFilters` 同样按参数存在性渲染，两种口径文案不共存。

### 8.4 注意

- `min_yearly_top_pct` / `min_yearly_years` 是 v3 专有 filter 键，
  `SharpeBoardProfile.filters` 是 `Record<string, number | boolean>`，直接读即可。
- 年度窗口固定 3 年（不含当年），**不要**用 `min_yearly_years` 当窗口大小——
  它是「其中至少几年达标」的门槛（2），窗口长度是硬编码 3。

## 9. 数据缺口周口径（11-14-sharpe-board-gap-weeks，2026-11-14）

后端契约见 [backend §21](../backend/fund-select/backend/contracts.md)。本节只记前端专属部分。

### 9.1 「近52周在榜」列渲染 `在榜/可评`

- 文案：`formatListedWeeks(listed, evaluable)` → `51/51`；`evaluable` 缺失（老后端）
  时只显示 `51`（**不能显示 `51/0`**）。
- 分母 = 该基金**有有效样本**的周数（数据缺口周不计入）。表头 `title` 与单元格
  `hover-tip` 都要说清分母口径。
- `hover-tip--wrap`（多行换行）用于这两列的长文案；`data-tip` 是 `content: attr()`
  的纯文本，**不要写 `\n`**（不换行），用「；」分隔。

### 9.2 「最近连续周数」列 tooltip

`consecutiveWeeksTip(consecutive, gapWeeks)`：说明「数据缺口周跳过、不中断，真实缺席
（可评却未上榜）才中断」+ 列出该基金的数据缺口周（ISO 日期）。

### 9.3 图表标注数据缺口周

- `buildSharpeChartOption` 新增入参 `gapWeeks`（来自 `diagnostics.gap_weeks`）；
  缺口周画**竖线 markLine**（标签「数据缺口周」），与夏普下限线共用同一 markLine 的
  `data` 数组。
- 标注挂在**第一条可见** series 上（图例隐藏的 series 不绘制 markLine）；全部隐藏时
  退回第一条。
- tooltip 命中缺口周时提示「数据缺口周：无榜 / 样本未更新（不计入在榜、不打断连续）」，
  **不**误报「本周无在榜记录」。
- `buildSharpeChartOption` 仍必须是**零依赖纯函数**（node:test 直跑，不 import echarts）。

### 9.4 规则说明卡

`SharpeBoardProfileCard` 新增 `gapWeeks` prop：窗口内有缺口周时追加一行
（周数 + 日期 + 成因 + 「不计入在榜、也不打断连续周数——图上以竖线标出」）。

### 9.5 注意

- `SharpeBoardItem` 新增 `evaluable_weeks: number` 与 `gap_weeks: string[]`；
  `SharpeBoardDiagnostics` 新增 `gap_weeks: string[]`（**三处同步**：
  `src/api/models.py` ↔ `src/lib/sharpe-board.ts` ↔ 页面消费）。
- 走势页 `/sharpe-trend` 复用同一 `SharpeChart` 组件，但走势接口没有榜单周概念 →
  传 `gapWeeks={[]}`（**必传**，否则 tsc 报缺 prop）。
- `near_12w` 未同步改口径（仍按最近 12 条观测），缺口周落在最近 12 周内时会差 1 周；
  已知不一致，另开任务。
- **本地端到端验证可行**（修正 §7.5 的旧结论）：`pnpm build` 后
  `BACKEND_URL=http://127.0.0.1:8195 npx next start -p 3105` —— 应用自带代理路由
  `src/app/api/funds/[...path]/route.ts` 会把 `/funds/api/*` 转发到 `BACKEND_URL`，
  不需要 nginx。本地后端用生产库副本起 uvicorn（`DATABASE_URL=sqlite:////tmp/xxx.db`），
  即可在浏览器里验证真实数据下的新口径。

### 9.6 Tests Required（补充 §6）

```bash
node --experimental-strip-types --test src/lib/sharpe-board.test.ts src/lib/sharpe-chart.test.ts
npx tsc --noEmit
pnpm build
```

- `formatListedWeeks`：`51/51`、`50/51`、`8/52`、evaluable 缺失 → `51`；
- `listedWeeksTip` / `consecutiveWeeksTip`：含分母口径与缺口周日期；
- 图表：缺口周竖线在 markLine 内（与下限线共存）、无缺口周时不画标记、
  tooltip 命中缺口周时提示正确、标记挂在第一条可见 series。

## 10. 在榜占比筛选 + 时间范围精简（11-14-sharpe-board-listed-pct-filter，2026-11-14）

后端契约见 [backend §23](../backend/fund-select/backend/contracts.md)。

### 10.1 「至少上榜」改为在榜占比

- `SharpeBoardFilters.minWeeks` → `minListedPct`（默认 **60**，可手动改 0~100）。
- URL 参数 `min_weeks` → `min_listed_pct`；默认值（60）不写进 URL。
- 输入框是 `type="number"` `min=0 max=100 step=1`，`title` 说明
  「在榜占比 = 在榜周数 ÷ 可评周数（该基金有有效样本的周数）；0 = 不限」。
- 判定在后端：占比 = `listed_weeks / evaluable_weeks × 100`（与表格 `在榜/可评` 同源），
  含等于；前端只负责传值，**不要**自己按 `listed_weeks/52` 算。

### 10.2 时间范围去掉「近 1 年」

- `SharpeRange` 去掉 `'1y'`；`RANGE_OPTIONS` 只留 3 项，按时长升序
  （3 个月 → 6 个月 → 近一年(52周)）。
- 旧 URL `?range=1y` 回落默认 `all`（同样 52 周视图，行为不变）。

### 10.3 注意

- `sharpeFiltersActive` 用 `DEFAULT_SHARPE_FILTERS.minListedPct`（60）作基准；
  `page.tsx` 的 `pageAffecting` 判定与 `clearDisplayFilters` 同步改名。
- 清空输入框 → 0（= 不限）；`Number('') = 0` 的坑必须显式判空串，避免误触。
- 「清除展示筛选」把占比重置为 60（不是 0）——回到默认视图，不是全放。

### 10.4 Tests Required（补充 §6）

- `minListedPct` 默认 60、URL 往返、越界回落 60、默认值省略不写 URL；
- 旧参数 `min_weeks=3` → 落默认 60；
- `RANGE_OPTIONS` 恰 3 项且不含 `1y`；`?range=1y` → `all`。
