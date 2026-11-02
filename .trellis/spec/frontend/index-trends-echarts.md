# Index-trends ECharts contracts（宽基趋势观察图表）

> 来源：10-29-index-trends 任务。apps/index-trends 的月K+回归通道图契约，
> 与 macro-echarts.md 平行（各自独立副本，改一处勿同步另一处）。
> Last verified: 2026-10-29
>
> 2026-11-02（11-02-index-trends-weekly）：历史/当前/周报已统一为完整周线拟合，
> 下方「完整周线契约」一节优先于月线口径描述。

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

Wrong：candleData 里塞 `null` 表示无 K 线月份，或在 category 轴的 K 线数组前加月份序号。
Correct：用 `"-"` 占位；K 线项为 `[open, close, low, high]`。序号会被当成开盘价，实体从 0 画到价格，看起来像柱状图。

Wrong：前端用 `ext最后月 > 拟合末月` 判断是否"未来延伸"。
Correct：读后端 `extend_note` 的语义标注。

## 完整周线契约（2026-11-02，11-02-index-trends-weekly）

### Scope / Trigger
apps/index-trends 的历史图、当前通道图和周报统一使用**完整周线**拟合。
改周坐标、周 K 解析、窗口/模型切换、周报文案或迁移兼容前必读。

### Contracts
- **周主键是自然周周一**（`week_start`），`week_end` 为其后第 6 天；x 轴必须摊到
  **所有自然周**（含休市时间槽）。休市周与未来周的 K 线位置用 `"-"` 占位，
  通道序列在该处留 `null` 断点，**不跨缺口连线**；未来周不是"休市"，文案要区分。
- **只有交易日历判定完整、且该周最后交易日 15:05 已过的周**才进入拟合与完整 K 线；
  进行中的当周只做投影，不参与训练。前端**不自己判断"本周是否结束"**，
  一律读后端 `data_cutoff_week` / `expected_cutoff_week` / `expected_close_date`。
- 摘要口径用「最近收盘」并标明该周进行中、不参与拟合；不要写成「已完成交易周」。
- **所有周字段用周单位**：`timeframe:week`、`sample_count`（样本周数）、
  `fit_start/fit_end`（周一）、`data_cutoff_week`、`projection_week`。
  不再出现 `months` / `data_cutoff_month` 这类月命名字段装周值。
- **snapshot_id 一致性**：当前摘要与图形必须来自同一 `snapshot_id`；
  两次请求不一致时重新取同一 `model_id`，不混画旧模型。
- **模型 kind 带 `_weekly` 后缀**（`trailing_10y_weekly`、`since_inception_weekly`、
  `historical_fixed_10y_weekly`）。旧 URL `model=trailing_120m/since_inception` 在前端
  映射到周线并 `replace` URL；请求**旧月线 `model_id`**时后端返回明确的"旧周期不可用于
  周线图"提示，前端不得静默换成别的模型。
- 未来延伸为 **52 个自然周（约 1 年）**，不要机械换算成 156 条有交易周。
- 周报去重键是 `指数|ISO周|weekly`；同一周已 `sent` 不重发。切换到周线后首次报告
  不与旧月线位置直接比较。

### Tests Required
`node --experimental-strip-types --test lib/candleData.test.ts`（周 K 解析、跨年 ISO 周、
休市/未来周占位、通道摊平不跨缺口相连）+ `pnpm exec tsc --noEmit` + `pnpm build`。
浏览器验证：双 Tab、4 个固定窗口+全历史、两个周线模型、周/周单位文案、
375px 与 1440px 无横向溢出、控制台无 ECharts 错误。
