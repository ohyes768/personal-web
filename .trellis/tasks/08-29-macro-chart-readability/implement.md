# 宏观图表可读性优化实施计划

## 1. 共享基础设施

- [x] 新增 `MacroPlot`，整合 `usePlotlyAutoResize`、响应式 layout 和统一空状态。
- [x] 重构 `plotlyTheme.ts`，提供基础 layout、时间轴、数值轴、trace 和 subplot domain builders。
- [x] 统一 `BASE_PLOT_CONFIG`，保留缩放/复位，去掉套索选择。
- [ ] 为轴编号、domain、数字格式和空序列过滤增加单元测试。（macro 包暂无测试框架，后续补）

## 2. 逐图迁移

- [x] `EconomicChart`：迁移两子图布局；补齐 hidden Tab 自动 resize，汇率 tooltip 同时展示原始值与相对变化，移除 Y 轴 `fixedrange`。
- [x] `RatesChart`：改为三子图，过滤空序列，调整高对比色与线型；显式绑定每条 trace 的 X/Y 轴并用 `matches` 联动日期轴。
- [x] `LiquidityChart`：改为 VIX、HIBOR、TGA 三子图。
- [x] `CommodityChart`：改为贵金属、能源/工业金属两子图，修正原油低对比色。
- [x] `StockIndexChart`：改为港/A 股、美股成长、道指三子图。
- [x] `MarketSentimentChart`：保留双轴，补短序列 marker 与统一 tooltip。
- [x] `HsgtFundFlowChart`：迁移到 MacroPlot / 统一主题。
- [x] `ComparisonChart`：预计算归一化涨跌供 tooltip 使用；3 种及以上单位按单位拆子图，删除错误强并轴行为。

## 3. 页面响应式

- [x] 经济页外边距已为 `p-4 sm:p-6 lg:p-8`。
- [ ] 检查 Tab、时间范围按钮、更新按钮在 375px 下的换行与可点击性。
- [x] 图例改为顶部横排，轴使用 automargin，高度按子图数量估算。

## 4. 验证

- [x] `tsc --noEmit` 通过
- [x] `pnpm build`
- [ ] 使用有完整 CSV 的本地或测试数据逐个切换 7 个图表 Tab。
- [ ] 桌面 1440px 截图检查。
- [ ] 平板 768px 截图检查。
- [ ] 手机 375px 截图检查。
- [ ] 检查 legend 点击隐藏、统一 hover、重置缩放、下载图片。
- [ ] 检查 0、1、2、少量点、全 null、部分 null 和完整长序列。
- [ ] 检查 hidden Tab 首次显示后宽度正确。
- [ ] 检查利率图各 trace 的 `xaxis/yaxis` 绑定及上下日期轴联动。
- [ ] 检查对比图归一化 tooltip 不含未解析表达式。

## 5. 后续

- ECharts 重构待办：`08-29-macro-echarts-refactor`（不在本任务实施）

## 6. 高风险文件

- `apps/macro/src/lib/utils/plotlyTheme.ts`
- `apps/macro/src/app/modules/economic/components/ComparisonChart.tsx`
- `apps/macro/src/app/modules/economic/components/RatesChart.tsx`
- `apps/macro/src/app/modules/economic/components/StockIndexChart.tsx`
