# Index-trends ECharts contracts（宽基趋势观察图表）

> 来源：10-29-index-trends 任务。apps/index-trends 的月K+回归通道图契约，
> 与 macro-echarts.md 平行（各自独立副本，改一处勿同步另一处）。
> Last verified: 2026-10-29
>
> 2026-11-02（11-02-index-trends-weekly）：历史/当前/周报已统一为完整周线拟合，
> 下方「完整周线契约」一节优先于月线口径描述。
> 2026-11-05：Web 周报生成与投递已移交 Hermes；仅保留数据刷新、图表和查询。
>
> 2026-11-02（11-02-index-trends-pe-percentile）：新增理杏仁 PE-TTM 近10年分位展示，
> 见下方「估值展示契约」。后端口径见
> [估值契约](../backend/index-trends/backend/valuation-contract.md)。

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
apps/index-trends 的历史图和当前通道图使用**完整周线**拟合。
改周坐标、周 K 解析、窗口/模型切换或迁移兼容前必读。

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
- Web 不提供周报设置或触发入口；历史周报数据保留。Hermes 只读数据 API 并自行调度投递。

### Tests Required
`node --experimental-strip-types --test lib/candleData.test.ts`（周 K 解析、跨年 ISO 周、
休市/未来周占位、通道摊平不跨缺口相连）+ `pnpm exec tsc --noEmit` + `pnpm build`。
浏览器验证：双 Tab、4 个固定窗口+全历史、两个周线模型、周/周单位文案、
375px 与 1440px 无横向溢出、控制台无 ECharts 错误。

## 估值展示契约（2026-11-02，理杏仁 PE-TTM 近10年分位）

### Scope / Trigger
当前通道摘要里的估值区域。改估值文案、单位或状态分支前必读。

### Contracts
- **单列一个估值区域**，不复用通道位置的标签、色调或百分比语义：
  通道位置 = 相对趋势通道；估值分位 = 相对自身历史估值。两者含义不同，注释里也要写明。
- **分位是主展示**（`percentile_pct`，1 位小数），PE 倍数、数据日期、总市值加权口径与
  理杏仁来源是辅助文本。
- **状态各有明确文案**：`ok` 正常展示；`stale` 展示数值并注明「未更新至 {target_date}」；
  `empty` = 暂无估值数据；`error` = 估值暂不可用（带缓存值时写明「缓存值（数据日期 …）」）；
  `disabled` = 未启用（未配置理杏仁访问令牌）。
- **旧后端不返回 `valuation` 字段时按「暂不可用」降级**，主图与通道摘要不受影响。
- 数值缺失渲染为「—」或隐藏，**不显示 0**。
- 估值与模型无关：切换两个模型时估值口径与数值不变（后端共享同一份估值）。

### Tests Required
`./node_modules/.bin/tsc --noEmit` + `npm run build`；浏览器验证 ok/stale/empty/error/disabled
五种状态、切换两个模型、刷新与缺模型场景，375px 无横向溢出。

### Wrong vs Correct
Wrong：把估值分位标成「低位/高位」区域；缺失值渲染成 0%；因为估值缺失而让主图报错。
Correct：独立区域 + 明确状态文案；缺值用「—」；主图与估值互不影响。
