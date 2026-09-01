# 宏观图表可读性优化设计

## 1. 结论

需要改组件，但不需要更换 Plotly。

改造分两层：

1. 增强共享图表基础设施，统一主题、坐标轴、图例、tooltip、响应式和空序列处理。
2. 按各 Tab 的指标语义调整子图和坐标轴，不能用一个“万能多轴图”覆盖所有场景。

不建议继续给 `buildMultiAxisLayout` 增加更多固定参数。现有函数把“暗色主题”和“多轴业务布局”混在一起，且默认右侧外置图例与固定大边距，不适合窄屏和子图。

## 2. 源码与渲染证据

### 2.1 共享层

- `apps/macro/src/lib/utils/plotlyTheme.ts:84-95` 默认边距为 `l:80, r:200`，图例固定在绘图区右侧。
- `apps/macro/src/lib/utils/plotlyTheme.ts:97-102` 的 X 轴只有颜色和网格，没有 `automargin`、刻度密度、格式、轴线或 spike 规则。
- `apps/macro/src/lib/utils/plotlyTheme.ts:130-145` 固定使用右侧竖排图例，窄屏会同时损失右侧边距和绘图区宽度。
- `apps/macro/src/lib/utils/chartConfig.ts` 与 `plotlyTheme.ts` 存在两套主题和 config，`EconomicChart` 未使用新的自动 resize 方案。
- 所有主要图表使用固定 700px 或 900px 高度，没有按子图数量和视口宽度统一计算。

### 2.2 单图问题

- `CommodityChart.tsx:27-41` 使用 4 个叠加 Y 轴。原油颜色 `#1e293b` 与图底 `#1a1a1a` 几乎没有对比度。
- `StockIndexChart.tsx:38-45` 使用 5 个叠加 Y 轴，右侧 3 个轴位置为 `0.92/0.95/0.98`，标题和刻度必然拥挤。
- `LiquidityChart.tsx:35-39` 使用 3 个不同单位的叠加轴，左侧主轴和左内轴压缩绘图区。
- `RatesChart.tsx:43-72` 多条线集中在红/粉色系，难以快速区分。空序列仍创建 trace 和轴配置。
- `RatesChart.tsx:109-127` 只绑定 `yaxis`，中国 10Y 与中国 10Y-2Y 没有绑定 `xaxis2`，可能与上方短端利率叠层；上下 X 轴也没有 `matches`。
- `MarketSentimentChart.tsx:41-45` 成交额与融资余额可共享金额轴，换手率可保留右轴，结构本身合理，但仍受共享图例、边距和刻度问题影响。
- `ComparisonChart.tsx:181-213` 的真实值模式只支持两个单位。`viewMode.ts:44-60` 会把第三种及以上单位强行并入右轴，量纲错误。
- `ComparisonChart.tsx:151-157` 在 hovertemplate 中使用 `%{y - 100:+.2f}`，Plotly 不支持模板内算术，归一化涨跌会显示错误。
- `EconomicChart.tsx:99-107` 未使用 `usePlotlyAutoResize`，hidden Tab 首次显示后可能维持错误宽度；旧配置还把 Y 轴设为 `fixedrange`。

### 2.3 实际渲染

本地 1536px 宽桌面环境中，利率图可见：

- 左右轴标题颜色接近且文字密集。
- 右侧轴刻度与曲线颜色竞争视觉注意力。
- SOFR、美债 3M、TED 无有效数据时仍保留布局逻辑，当前只剩 DR007 和中债序列，图表叙事不完整。
- 模式栏在暗色背景上对比不足。

本地商品 CSV 缺失，因此无法用当前数据完成商品图实拍验证。其 4 轴拥挤和原油低对比色可由源码直接确认。

## 3. 共享组件边界

### 3.1 新增 `MacroPlot`

建议新增轻量包装组件，不做业务数据拼装，只负责：

- `ResizeObserver` 和 hidden Tab 恢复可见后的 resize。
- 根据容器宽度生成 desktop/mobile layout。
- 统一 Plotly config、modebar、字体和背景。
- 统一 loading、empty、error 的图表区域尺寸。
- 接收 `data/layout/height/subplotCount`，保留 Plotly 原生能力。

### 3.2 拆分共享 builders

将 `plotlyTheme.ts` 拆成可组合能力：

- `buildBaseLayout(viewport)`：背景、字体、hoverlabel、图例、边距。
- `buildTimeAxis({ isBottom, compact })`：日期格式、刻度密度、网格、spike、`automargin`。
- `buildValueAxis({ title, color, unit, side })`：单位、数值格式、轴线、`automargin`、零线。
- `buildTrace(meta, x, y)`：线宽、dash、hovertemplate、空序列过滤。
- `buildSubplotDomains(count)`：2 至 3 个上下子图的 domain 和间距。

不把指标元数据放入共享层。label、unit、color、dash、分组仍由各 Chart 组件定义。

## 4. 图表结构

### 中美利差/汇率

- 保留两张上下联动子图。
- 上图：中美收益率，颜色与虚实线同时编码。
- 下图：汇率相对变化。
- 迁移到统一主题和 `MacroPlot`。
- 汇率 trace 通过 `customdata` 同时保留原始汇率，tooltip 展示原始值与相对变化。
- 去掉不必要的 Y 轴 `fixedrange`，允许用户局部缩放后双击复位。

### 利率利差

- 三个共享日期轴的子图：
  1. DR007、SOFR、美债 3M。
  2. TED 利差。
  3. 中国 10Y、中国 10Y-2Y。
- 每个子图最多 2 个 Y 轴。
- 无有效值的序列不创建 trace，也不进入图例。
- 每条 trace 显式绑定所属 `xaxis` 与 `yaxis`，所有日期轴通过 `matches` 联动。

### 流动性/风险

- 三个上下联动子图：VIX、HIBOR、TGA 各自单轴。
- 原因是三个指标单位和经济含义都不同，叠加并不能增加比较价值。

### 商品

- 两个上下联动子图：
  1. 黄金与白银，各自一侧轴。
  2. 原油与铜，各自一侧轴。
- 每个子图最多 2 个轴，修正原油为高对比蓝色。

### 股指

- 三个上下联动子图：
  1. 恒生与上证。
  2. 标普 500 与纳斯达克。
  3. 道琼斯。
- 前两个子图最多 2 个轴，第三个单轴。
- 保留真实点位，归一化比较继续由“对比”Tab 负责。

### 市场情绪

- 保留一张双轴图。
- 成交额与融资余额共用左轴，换手率用右轴。
- 短序列启用 marker，只有 1 个点时也能看到数据。

### 对比

- 百分位和起点归一模式保留单轴。
- 起点归一模式预先计算“相对 100 的涨跌”到 `customdata`，tooltip 只引用字段，不执行表达式。
- 真实值模式：
  - 1 至 2 种单位时使用双轴。
  - 3 种及以上单位时按单位拆分子图，禁止把不同单位强并到右轴。
- 相关性子图保持独立固定范围 `[-1, 1]`。

## 5. 视觉规则

- 暗色底使用高对比、色盲相对安全的离散色板。
- 同图曲线除颜色外再使用实线、虚线、点划线辅助区分。
- 主线宽 2.5px，次线 2px。短序列或少于 8 个有效点时显示 marker。
- 网格线降低存在感，轴线和刻度比网格稍亮。
- 仅最底部子图显示 X 轴标题，上方子图只显示必要刻度。
- 数字使用 tabular nums，按单位统一格式化：
  - 百分比 2 至 3 位小数。
  - 指数点位千分位、0 至 1 位小数。
  - 亿元千分位、0 至 2 位小数。
- tooltip 使用统一日期头，同一子图按日期聚合显示，禁止重复输出“日期”行。
- 桌面图例置顶横排，窄屏置顶并缩小字号，减少右侧固定留白。

## 6. 响应式

- `>= 768px`：完整轴标题、横排图例、每个子图约 240 至 280px 高。
- `< 768px`：页面外边距缩小，隐藏重复轴标题，只保留单位短标签；减少 X 轴刻度；图例字号 11px；modebar 仅保留下载与重置。
- 坐标轴必须使用 `automargin: true`。
- 图表总高度由子图数量计算，不再由每个组件随意写死。

## 7. 风险与回滚

- 子图增多会增加页面高度，但换来可读性，且用户已确认接受 2 至 3 个联动子图。
- Plotly 多子图轴编号容易出错，需为 layout builder 增加单测。
- hidden Tab resize 行为必须保留，`MacroPlot` 应复用现有 `usePlotlyAutoResize`。
- 改造可按图表逐个迁移，旧组件可在每次迁移前独立回滚。
