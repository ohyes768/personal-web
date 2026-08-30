# 宏观图表 ECharts 重构

## Goal

在完成当前 Plotly 可读性优化之后，用 Apache ECharts 重构宏观经济页各 Tab 时序图，提升移动端适配、包体积控制和统一视觉能力。

## Status

**后续待办，暂不实施。**

前置条件：`08-29-macro-chart-readability` 完成并稳定使用一段时间。

## Background

- 当前宏观图表使用 `react-plotly.js`。
- Plotly 已能覆盖多子图、多轴、统一 hover 等需求，但包体积大，移动端与默认视觉需要较多手工配置。
- ECharts 在多 grid、dataZoom、axisPointer、按需引入和中文生态上更适合后续产品化重构。
- 本任务不阻塞当前 Plotly 优化。

## Requirements

### R1 替换范围

- 替换利率、中美利差/汇率、流动性、商品、股指、市场情绪、对比共 7 个图表 Tab。
- 信号首页卡片不在范围内。
- 保留现有数据接口、Tab 按需加载和独立日期轴语义。

### R2 能力对等

- 支持 2 至 3 个共享日期轴联动子图。
- 支持双轴、统一 tooltip、图例、缩放/复位、空值断线。
- 桌面与 375px 窄屏可读。

### R3 迁移策略

- 先抽 ECharts 共享主题与 `MacroEChart` 包装组件。
- 按 Tab 逐个迁移，允许过渡期 Plotly / ECharts 并存。
- 迁移完成后移除 `react-plotly.js` 与无用 Plotly 工具函数。

## Acceptance Criteria

- [ ] 7 个图表 Tab 全部迁移到 ECharts，行为与当前 Plotly 优化版对等。
- [ ] 包体积与首屏加载相对 Plotly 版有可测量改善或明确取舍说明。
- [ ] 桌面 1440px 与手机 375px 图表可读，无轴标签裁切。
- [ ] 旧 Plotly 依赖与死代码已清理。

## Out of Scope

- 现在立刻开始实现。
- 改后端数据契约。
- 信号首页重构。

## Notes

- 创建原因：用户确认“先优化 Plotly，后面再建 TODO 使用 ECharts 重构”。
- 依赖任务：`08-29-macro-chart-readability`
