# 宏观信号日频指标月度口径(B+C):月均字段透传与当月/历史月分层展示

## Goal

宏观信号页整体按月度展示，日频指标(DR007、美元指数、两市成交额等)目前只留
「最后一次推送日的单日读数」，存在两个问题：

1. **当月不够新**：月频推送节奏下，月中看当月卡片，日频指标可能停留在月初值。
2. **历史月代表性不准**：单日读数噪声大，用「碰巧那天」的值定档位不可靠。

方案 B+C 组合：

- **B(调度侧，仓库外)**：日频重的 skill(monetary-policy、exchange-rate、
  risk-appetite)改为交易日盘后推送，月频 skill 照旧月度跑。后端按月留存机制
  已支持同月重推幂等，当月卡片自动跟随最新推送、历史月自动定格。
- **C(本仓库)**：skill 输出契约增加日频指标的 `month_avg`(月均值)字段，
  后端透传、前端分层展示——**当月卡片显示最新日度值，历史月卡片显示月均**。

本任务只做 C 的仓库内改动 + B 的调度脚本/文档说明；skill 侧输出 `month_avg`
属于 macro-fin-skill 仓库的配套改动，在本任务文档中登记契约、不实现。

## Requirements

### R1 后端模型扩展

- `MacroIndicator` 新增 `month_avg: Optional[float]` 字段(仅日频指标有值，
  月频为 null)。
- skill JSON 的读取来源：
  - `macro_signal.json`: `indicator_meta[key].month_avg`
  - `risk_data.json`: `data.{volume,turnover,margin}.month_avg`
- 字段缺失时为 null，不影响现有字段解析(向后兼容：旧 skill 输出不推
  month_avg 也能正常工作)。

### R2 前端分层展示

- 历史月卡片(所选月 < 当前自然月)：日频指标若有 month_avg，主数值位置显示
  月均值，并标注「月均」；无 month_avg 时回退当前行为(显示单日值，标注「日频」)。
- 当月卡片(所选月 = 当前自然月)：行为不变，显示最新日度值 + 「日频」标签。
- 月频指标不受影响。

### R3 文档更新

- `docs/MACRO_SIGNAL_API.md`: 登记 `month_avg` 字段契约(来源、类型、
  何时有值)。
- `docs/宏观信号按月留存设计.md` 或新文档：登记 B 方案的推送调度约定
  (哪些 skill 日度推、哪些月度推)，供 macro-fin-skill 侧实施对照。

## Acceptance Criteria

- [ ] AC1 后端：skill JSON 带 `indicator_meta.dr007.month_avg=1.68` 时，
  `GET /api/macro/signal` 返回的 dr007 指标含 `month_avg=1.68`;
  无该字段的旧格式 JSON 解析不报错、month_avg=null。
- [ ] AC2 后端：risk_data.json 的 `data.volume.month_avg` 同样透传到
  `total_amount_yi` 指标。
- [ ] AC3 前端：历史月卡片中日频指标显示「月均值 + 月均标注」；skill 未输出
  month_avg 时回退显示单日值(不比现状差)。
- [ ] AC4 前端：当月卡片日频指标显示行为与现状一致(最新值+日频标签)，
  month_avg 不干扰当月展示。
- [ ] AC5 `pnpm lint` 通过；后端 `pytest tests/ -v` 全绿(含新增测试)。
- [ ] AC6 文档登记完成(MACRO_SIGNAL_API.md + 调度约定文档)。

## Notes

- `updated_at` 兼容别名仍在过渡期，本任务不动它。
- B 方案跨月归档细节(9 月 1 日推 8 月 31 日数据归哪月)已在归档提取逻辑中
  以 data_date 口径处理，本任务不重复设计。
- 月均值由 skill 侧计算(全月或本月至今均值)，后端只透传不计算——延续
  「后端 = IO + 格式转换，不重新实现 skill 逻辑」的边界。
