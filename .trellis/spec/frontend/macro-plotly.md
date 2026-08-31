# Macro 前端 Plotly 契约(apps/macro)

> 来源:2026-08-31 联动子图拆分与两次线上全空白故障的实战结论。
> 以下每条都对应一次真实故障,改动 Plotly 相关代码前必读。

---

## 1. 传给 Plotly 的对象不得含显式 `undefined` 值的键(trace 与 layout 都算)

- **故障**:trace 带 `marker: undefined`(键存在、值为 undefined)时,
  `cleanData` 里 `'marker' in trace` 命中 → 对 undefined 做 `'line' in undefined`
  → TypeError,newPlot 中断,图表空白且**控制台零报错**。
- **规则**:构造 trace/layout 后过 `omitUndefined`(plotlyTheme.ts)。
  写法上宁可条件展开(`...(cond ? { marker: {...} } : {})`),
  不要三元返回 undefined 属性。

## 2. 注入 Plotly 的数组必须拷贝,禁止共享引用

- **故障**:联动子图把 state 里的 range 数组直接放进 `layout.xaxis.range`,
  Plotly 拖拽缩放时**原地改写该数组**,导致联动值比较永远相等、第二次起联动失效。
- **规则**:`range: xRange ? [...xRange] : undefined`(见 buildSubplotLayout)。
  任何进入 Plotly 的可变结构都按"值类型"对待:注入拷贝、比较用值。

## 3. relayout 事件有两种 key 形态,联动处理两者都要接

- 用户拖拽/框选缩放:`{ 'xaxis.range[0]': v0, 'xaxis.range[1]': v1 }`(分开的键)
- 程序性 relayout:`{ 'xaxis.range': [v0, v1] }`(完整数组)
- 双击复位:`{ 'xaxis.autorange': true }`
- 见 LinkedSubplots.handleRelayout,遗漏第一种 = 联动完全不工作。

## 4. doubleClick 用 'autosize',不用 'reset'

- 'reset' 恢复的是 **hidden Tab 首绘时的旧快照**(数据切片前,范围可能完全错误,
  实测出现 2000-01-01);'autosize' 回到当前数据的自动范围,联动复位天然一致。

## 5. react-plotly.js 会静默吞错

- `Plotly.react` reject 时,只有传了 `onError` prop 才会上报,否则无声。
- MacroPlot 已透传 `onError`(console.warn);新增图表包装时必须保留。
- 排查空图表时先看 `.js-plotly-plot` 容器:`_fullLayout` 缺失 / main-svg = 0
  = newPlot 没跑完;零报错基本等于本条 + 第 1/2 条之一。

## 6. 架构:联动子图 = 独立 Plot 实例 + 事件同步

- plotly.js **不支持多 legend**(单实例只有一个图例框),
  "图例归各子图"只能拆独立实例:LinkedSubplots(N 个 MacroPlot)+
  buildSubplotLayout(单子图 layout)+ onRelayout 同步 x 轴。
- 轴 key 沿用原命名(子图二用 x2/y3),组件数据层不需要归一化。

## 7. 本地验证环境注意

- `next dev`(3001)与 `next build/start`(3000)**共写 `.next` 会互相污染产物**
  (chunk MODULE_NOT_FOUND / 500)。生产验证前先停 dev。
- 图表交互(拖拽缩放)必须用真实 CDP 输入验证(playwright-cli mouse),
  合成 MouseEvent/PointerEvent Plotly 不认;双击要用真实 dblclick。
