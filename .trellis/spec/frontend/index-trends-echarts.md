# Index-trends ECharts contracts（宽基趋势观察图表）

> 来源：10-29-index-trends 任务。apps/index-trends 的月K+回归通道图契约，
> 与 macro-echarts.md 平行（各自独立副本，改一处勿同步另一处）。
> Last verified: 2026-10-29

## Scope / Trigger

apps/index-trends 中 TrendChart（ECharts 6 candlestick + line 叠加）的渲染契约。
修改图表系列、延伸区语义、x 轴或 tooltip 前必读。

## Contracts

- **ECharts candlestick 的 data 不接受 `null` 项**：无 K 线的 x 轴位置（如未来延伸月）
  必须用字符串 `"-"` 占位，否则 `getInitialData` 抛
  `Cannot read properties of null (reading 'value')`，整图崩溃。
- 拟合区实线 / 延伸区虚线拆成独立 line series；延伸序列首点由后端填入拟合末端值，
  前端不做连线拼接。缺月位置补 `null`（line 类型接受 null 断线）。
- 延伸区 markArea 的语义（"趋势延伸（非预测目标）" 浅蓝 vs "后续观察区（模型不变）" 暖黄）
  由后端 `extend_note` 字段驱动，前端不做日期推断——观察区可跨越当前月之前，
  字符串比较月份会误判（2026-09 实测踩坑）。
- 隐藏容器（clientWidth/Height 为 0）不调用 echarts.init；初始化前用
  `echarts.getInstanceByDom(el)` 复用已有实例再 setOption(option, true)，
  避免 StrictMode 双挂载下 "chart instance already initialized" 警告。
- dataZoom 只缩放画面；组件内不得有任何重拟合逻辑（拟合全在后端，模型版本幂等）。

## Tests Required

`pnpm exec tsc --noEmit` + `pnpm build`；浏览器实际验证：Tab 切换（含隐藏→显示）、
窗口/模型切换后数值全部来自所选模型、375px 无横向溢出、控制台无 ECharts 错误。

## Wrong vs Correct

Wrong：candleData 里塞 `null` 表示无 K 线月份。
Correct：用 `"-"` 占位；K 线项为 `[index, open, close, low, high]`。

Wrong：前端用 `ext最后月 > 拟合末月` 判断是否"未来延伸"。
Correct：读后端 `extend_note` 的语义标注。
