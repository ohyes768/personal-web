# 宏观联动子图拆独立实例,图例归各子图上方

## Goal

宏观页 6 个联动子图组件(上下 2~3 个子图共享日期轴)目前是单 Plotly 实例,
图例统一显示在整个图表最顶部。改为每个子图一个独立 Plot 实例,图例(legend)
显示在各自子图上方横排,并保留子图间 x 轴缩放联动。

## Background

- `buildLinkedSubplotLayout`(apps/macro/src/lib/utils/plotlyTheme.ts:279)用单实例
  `layout.grid` + `xaxisN.matches` 实现上下子图联动,图例是全局唯一一个、顶部横排
  (plotlyTheme.ts:196-205)。
- plotly.js 2.35.2 **不支持多 legend**(一个 layout 只有一个 legend 对象),
  无法在单实例内让图例跟随子图。
- 用户明确要求:各子图的曲线图例显示在各子图上方(横排)。

## Requirements

### R1 拆分独立实例

- 6 个组件拆为每子图一个 `<Plot>`(经 MacroPlot)纵向排列:
  EconomicChart、CommodityChart、ComparisonChart(各 2 子图);
  LiquidityChart、RatesChart、StockIndexChart(各 3 子图)。
- 每个子图独立 layout,复用 buildBaseLayout 的顶部横排 legend 配置
  (orientation h / y 1.02),自动落在该子图上方。

### R2 x 轴联动保留

- 任一子图拖拽/框选缩放、双击复位时,其余子图 x 轴同步(range 或 autorange)。
- 双向同步,不得死循环;同步延迟应无感知。

### R3 不回退已修复的两个坑

- 不引入显式 `undefined` 键进 trace/layout(Plotly cleanData 崩溃,见 d413f28)。
- hidden Tab 首次渲染不得出现 0 高/空白(usePlotlyAutoResize 机制保留)。

### R4 视觉与交互不降级

- 子图间距合理,整体高度与现状相近或更清晰;hover tooltip、spike、
  点击图例隐藏曲线等交互保留。
- 窄屏(容器 < 700px)下图例可换行,不遮挡绘图区。

### 范围外

- MarketSentimentChart / HsgtFundFlowChart(单图多轴,图例本就在自己上方)不动。
- ComparisonChart 的指标选择器交互逻辑不动,仅换渲染层。

## Acceptance Criteria

1. 浏览器实测 6 个 Tab:每个子图上方有自己的横排图例,只含该子图的曲线;
   顶部不再出现全局统一图例。
2. 任一子图拖拽缩放 → 其余子图同步;双击复位 → 全部复位;无死循环/卡顿。
3. 点击任一子图图例条目 → 仅该子图对应曲线隐藏,其余子图不受影响。
4. `document.querySelectorAll('.js-plotly-plot')` 每子图均 `_fullLayout` 存在、
   main-svg > 0,零空壳;console 无图表相关报错。
5. 切 Tab(hidden → visible)后图表正常显示尺寸,不残留 0 高。
6. `pnpm build` 通过,lint/type-check 无新增错误。

## Constraints

- 技术栈不变:react-plotly.js 2.6.0 + plotly.js 2.35.2,不引入新依赖。
- 不改后端与 API。
