# fund-select 夏普榜单页前端契约（2026-11-05，任务 11-04-fund-sharpe-weekly-board）

独立 Tab「夏普榜单」：`src/app/sharpe-board/page.tsx` → URL `/funds/sharpe-board`。只读页面（数据全部来自 `GET /api/funds/sharpe-board`，后端契约见 `../backend/fund-select/backend/contracts.md` §13），页面内所有筛选都是**展示筛选**，绝不触发采集；采集入口只有复用的 `SchedulerDialog`（齿轮）。

## 1. 路由与请求

- 五 Tab 公共导航是 `src/components/FundsNavigation.tsx`，`FundsHeader` 与新页共用；`FundsTab`/`exportKind` 仍只代表四个采集来源，**不得**把夏普榜单伪造进刷新来源。旧四页除导航组件替换外零行为变化。
- basePath 契约同 contracts §4：`<Link>` 用相对路径（`/sharpe-board`）；`fetch` 必须写全路径 `/funds/api/funds/sharpe-board`；URL 同步只拼 `?qs`。
- `src/lib/sharpe-board.ts` 独立持有 TS DTO（对齐后端 6 个 `SharpeBoard*` DTO）、URL 参数 parse/serialize（**默认值省略不写**：source=discovery-stock、range=all、page=1、min_weeks=1 都不落 URL）、`fetchSharpeBoard`。**source 切换必须 AbortController 中止旧请求**，否则旧来源响应会覆盖新来源状态。
- 后端 DTO 加字段时三处同步（同 §3a 三处清单）：`src/api/models.py` ↔ `src/lib/sharpe-board.ts` ↔ 页面消费；枚举值（source/range/status）两端字面一致。

## 2. ECharts 图表

- `echarts ^6` 装在本 app（pnpm，锁文件一起改）；仅新页 `dynamic(() => import(...), { ssr: false })`；不跨应用 import。`src/lib/sharpe-chart.ts` 是**零依赖纯 option 构造**（不 import echarts/React），node:test 直跑；`SharpeChart.tsx` 只管实例生命周期（init/ResizeObserver/dispose、隐藏或零尺寸容器不 init）。
- 图合同（option 测试锁定）：`connectNulls:false`、`smooth:false`、缺席周断线留空、单点可见——孤立点用 `isolatedPoints` 标记后 `showSymbol:true` + `symbolSize` 回调（孤立点 4px，连续点 0）。**不要**用 `showSymbol:false`（孤立单点完全不渲染）也不要全量 symbol（300 线铺满画布）。纵轴不强制从零、夏普下限参考线、series=全部命中基金（不随列表分页截断）。
- **翻页/筛选重拉不重建图**：图表 effect 依赖 `dataSignature`（`JSON.stringify([weeks, series.map(s => [s.code, s.values])])`）而非数组引用——翻页时 series 内容不变，实例存活，dataZoom/tooltip 状态保留；数据真变（source 切换/新周）签名变化照常重建。图例状态以 React 为单一真相源（`legendselectchanged` 回传父组件），隐藏集变化走 merge `setOption({legend:{selected}})` 不重置缩放。
- 列表行「聚焦」按钮联动图例高亮，「恢复全部」清空 hidden 与聚焦。

## 3. 状态与文案

五种状态必须区分，不能都渲染成「暂无数据」：首次无数据（库空）、请求失败（可重试）、成功空榜 vs 采集失败（StatusBar：失败红条带 errors、样本未更新灰条、stale 提示「旧榜日期不冒充本周」）、展示筛选无匹配（带「清除展示筛选」）、时间范围内无点（列表保留，图不造点）。字段文案是「最近上榜夏普」，不得写成「当前夏普」；「最近连续周数」含义是最近一段连续在榜（缺席中断）。

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
