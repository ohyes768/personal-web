# 执行计划

## 前置

- 基线:`pnpm build` 通过;浏览器记录当前 6 Tab 图例/联动表现作为对照。
- 本地起后端(8094)+ 前端生产模式(3000)用于每步验证。

## Step 1 布局工厂:buildSubplotLayout + SubplotPanelSpec

- plotlyTheme.ts 新增 `SubplotPanelSpec` 类型与 `buildSubplotLayout`。
- 单子图 layout:buildBaseLayout(顶部横排 legend)+ x 轴(无 matches)+
  本子图 y 轴;所有对象 omitUndefined 包裹。
- 验证:`pnpm build` 通过;tsc 无新错误。

## Step 2 MacroPlot 透传 onRelayout

- MacroPlot 新增 `onRelayout` prop 透传给 `<Plot>`。
- 验证:build 通过。

## Step 3 新组件 LinkedSubplots

- `components/LinkedSubplots.tsx`:管理共享 xRange、防循环容差比较、
  autorange 复位、逐 panel 渲染 MacroPlot(含空 panel 占位)。
- 验证:build 通过(此时尚无调用方)。

## Step 4 迁移 6 个组件(每个独立可验证,顺序从简到繁)

4a EconomicChart(2 子图,结构最简,验证联动核心链路)
4b CommodityChart(2 子图)
4c StockIndexChart(3 子图)
4d LiquidityChart(3 子图)
4e RatesChart(3 子图)
4f ComparisonChart(2 子图,有指标选择器,最后迁移)

每个组件:
- useMemo 产出 `subplots: SubplotPanelSpec[]`(traces 按子图分组,轴 key 不动)
- 渲染换 `<LinkedSubplots>`
- 验证(每步都跑):
  - build 通过
  - 浏览器该 Tab:子图各自图例、拖拽联动、双击复位、图例点击隐藏
  - `.js-plotly-plot` 零空壳(`_fullLayout` 全存在)
  - 切走再切回 Tab(hidden→visible)尺寸正常

## Step 5 清理

- 确认 buildLinkedSubplotLayout 无调用方后删除(含 XAxisKey 若不再需要)。
- 全局 grep `matches:` 确认无残留联动引用。
- 验证:build + 全 Tab 遍历(DOM 断言 6 Tab 全部图例/联动/零空壳)。

## Step 6 全量验证(最后一轮全范围检查)

```bash
cd apps/macro && pnpm build && pnpm lint
```

浏览器全 Tab 遍历脚本断言:
- 每个 Tab 每子图 main-svg > 0、_fullLayout 存在
- 每子图 legend 条目数 = 该子图 trace 数,且各子图 legend 内容互不混杂
- console 无 error

## Review Gates

- Step 3 后(联动机制成型)与 4a 后(首个组件验证)各停一次自查:
  若联动出现死循环/卡顿,回到 design.md §2.3 重审同步策略。
- Step 4 每个子步骤是一个回滚点(revert 单组件)。

## 回滚

- 任一组件迁移后异常:revert 该组件 commit,其余 Tab 不受影响。
- 整体回滚:revert Step 1-3 commit 后各组件自动回到 buildLinkedSubplotLayout。
