# 技术设计:联动子图拆独立实例

## 1. 边界与分层

```
Chart 组件 (EconomicChart 等 6 个)
   │  只负责:把业务数据按子图分组,产出 subplots: SubplotPanelSpec[]
   ▼
LinkedSubplots (新组件,联动编排层)
   │  职责:共享 x range 状态、防循环、渲染 N 个 MacroPlot
   ▼
MacroPlot (现有渲染壳,小改)
   │  新增:透传 onRelayout;接受注入的 xaxis.range
   ▼
plotlyTheme.ts (布局工厂)
   │  新增 buildSubplotLayout(单子图);buildLinkedSubplotLayout 保留过渡期后删除
```

## 2. 核心契约

### 2.1 SubplotPanelSpec(新类型,plotlyTheme.ts 导出)

```ts
export interface SubplotPanelSpec {
  /** 本子图的 traces(轴 key 沿用现有 y/y2/x 等命名,不改组件数据层) */
  traces: Data[];
  /** 本子图轴规格(现 SubplotSpec 结构不变) */
  spec: SubplotSpec;
  /** 可选:覆盖高度 */
  height?: number;
  /** 可选:空状态文案 */
  emptyMessage?: string;
}
```

关键决策:**trace 的 xaxis/yaxis key 不归一化**。拆分后每个子图独立 layout,
layout 里只写该子图 spec 涉及的轴(如子图二只写 xaxis2/yaxis3),Plotly 按
trace 引用的轴名自动配对,组件数据层零改动。

### 2.2 buildSubplotLayout(新函数)

```ts
export function buildSubplotLayout(opts: {
  spec: SubplotSpec;          // 单个子图
  isBottom: boolean;          // 是否最底子图(决定日期轴标题/automargin)
  compact?: boolean;
  margin?: {...};
}): Partial<Layout>
```

- 内部 = buildBaseLayout(自带顶部横排 legend)+ 该子图的 x 轴(不再有 matches)
  + 该子图的 y 轴们;omitUndefined 包裹(遵守 d413f28 的教训)。
- 无 grid 字段;高度由 MacroPlot 的 height prop 控制。

### 2.3 x 轴联动(LinkedSubplots 核心逻辑)

```tsx
const [xRange, setXRange] = useState<[number, number] | null>(null);
// null = autorange(初始/复位态)

const handleRelayout = useCallback((idx: number, e: PlotlyRelayoutEvent) => {
  // 1. 从事件提取本子图 x 轴变化:key 形如 `${xKey}.range[0]` / `${xKey}.range`
  //    / `${xKey}.autorange`
  // 2. autorange:true → setXRange(null)
  // 3. 新 range 与当前 xRange 逐值比较(容差 1e-9),相同则跳过(防循环:
  //    Plotly.relayout 程序性修改同样触发 relayout 事件)
  // 4. setXRange(newRange)
}, [xRange]);

// 注入:每个子图 layout 的 xaxis.range = xRange ?? undefined(omitUndefined 剥)
```

- 事件来源:react-plotly.js 原生 `onRelayout` prop(eventNames 含 'Relayout')。
- 复位路径:双击触发 `xaxis.autorange: true` 事件 → xRange=null → 所有子图
  layout 的 range 被 omitUndefined 剥掉 → Plotly 回到 autorange。
- 时间轴是 date 字符串(range 为日期字符串),比较用字符串相等即可,无需数值化。

### 2.4 MacroPlot 小改

- 新增可选 props:`onRelayout?: (e: unknown) => void`,直接透传给 `<Plot>`。
- 其余不动:usePlotlyAutoResize(hidden tab 修复)、omitUndefined、空数据占位。

## 3. 数据流(以 EconomicChart 为例)

```
data → useMemo → subplots: SubplotPanelSpec[] = [
  { traces: [美债3M/2Y/10Y, 中国10Y], spec: { xAxisKey:'x', yAxes:[y 收益率] } },
  { traces: [美元指数, USD/CNY, USD/JPY, USD/EUR], spec: { xAxisKey:'x2', yAxes:[y2 汇率] } },
]
     → <LinkedSubplots subplots={subplots} />
        → 每个 panel: <MacroPlot data=traces layout=buildSubplotLayout(spec)
                        height=chartHeightForSubplots(1) onRelayout=... />
```

## 4. 权衡与备选

| 决策 | 备选 | 取舍理由 |
|------|------|----------|
| 拆独立 Plot 实例 | annotations 手绘伪图例 | 伪图例无点击交互、对齐困难;拆实例是 Plotly 社区标准做法 |
| JS 事件同步联动 | 保留单实例 + matches | 单实例无法多 legend,与需求冲突 |
| 轴 key 不归一化 | 全部重映射为 x/y | 后者要求 6 个组件数据层全改,风险大收益零 |
| range 容差比较防循环 | "同步中"标志位 | 程序性 relayout 与用户操作无法可靠区分;值比较更简单可靠 |

已知代价:拆分后每个子图是独立 SVG,Plotly 包体积不变但实例数 2~3 倍,
6 Tab 常驻挂载约 15 个实例;实测关注首屏渲染耗时,若明显劣化再评估
(缓存 chunk 后实例创建开销约几十 ms 级,预期可接受)。

## 5. 兼容与回滚

- 分步迁移:plotlyTheme 新函数先行,组件逐个切换,buildLinkedSubplotLayout
  全部调用方迁完后删除(避免死代码)。
- 每迁移一个组件即可独立验证(该 Tab 图例+联动),出问题单组件回滚,
  不影响其余 Tab。
- 回滚点:git revert 单组件 commit 即可恢复该 Tab 单实例布局。
