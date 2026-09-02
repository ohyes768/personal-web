# 股票基金筛选-第二阶段（业绩基准+风险指标）

## Goal

承接 `09-02-stock-fund-select-tab`（已归档）PRD 中显式后置的第二阶段指标：

- 业绩比较基准（TRI）同期收益 + 超额收益
- 信息比率 IR = `(R_p − R_b).mean() / std × √252`
- 夏普比率 Sharpe = `(R_p − R_f).mean() / std × √252`
- 选股能力 α（T-M 回归截距，年化）
- 择时能力 γ（T-M 二次项系数）
- 选股 α IR = `α / σ_residual × √252`

第一阶段已交付 `/funds/stock` 独立路由 + 默认筛选 + achievement 排名；本阶段叠加风险/超额维度。

## 任务地图（parent 不直接写代码）

| 子任务 | 交付物 | 状态 |
|---|---|---|
| `09-02-stock-fund-select-phase2-infra`（A） | benchmarks.yaml + benchmark_fetcher + risk_free_fetcher + 2 张表 + 迁移 + refresh 接入 | planning（prd/design/implement 已备） |
| `09-02-stock-fund-select-phase2-indicators`（B） | risk_service（Sharpe/IR/T-M/α-IR）+ FundRiskMetrics 表 + API + 前端列 | planning（prd 已备；design/implement 待 A 落地后写） |

**依赖**：B 依赖 A 的 `fund_benchmark` / `risk_free_rate` 表与 fetcher 输出；A 不依赖 B。顺序 A → B，不允许并行。

## 跨子任务验收（parent 持有）

- [ ] A + B 全部子任务 archive 后，`/funds/stock` 页表格可见 6 个新列：Sharpe / IR / 选股α / 择时γ / α-IR / 超额收益（近 3 年窗口），空值显示 "—"
- [ ] 143 只股票基金中 ≥ 142 只能计算并展示 IR / Sharpe（968157 无基准字段除外，显示 "—"）
- [ ] 债基 tab（`/funds`）行为零变化：现有 pytest 全过 + 前端构建过
- [ ] 全链路一次跑通：`refresh_stock_funds_sync`（含 benchmark + risk 步骤）→ API 返回 → 前端展示，无 schema 错误
- [ ] 后端 `uv run pytest tests/ -v` 全过；前端 `pnpm exec tsc --noEmit` 0 错 + `pnpm build` 过

## Constraints

1. 不动债基任何逻辑（筛选 / refresh / 前端）
2. 不引入新外部数据源（akshare 覆盖）与新 .env 变量
3. Python 3.13 兼容，不引 empyrical / quantstats
4. 指标计算窗口统一为近 3 年（与第一阶段 dd_3y 口径一致）
5. parent 本身不开 implement；工作全部在子任务内完成

## Notes

- 调研资产：`tmp/demo_benchmark_extract_143.py`（143 只公式提取报告 `tmp/benchmark_extract_report.json`）、`tmp/probe_*.py`（利率源探测）
- A 的关键调研结论已固化到 A 的 prd.md「Background」：字段覆盖 99.3%、57% 公式含「存款」成分、`bond_zh_us_rate` 无 1Y 只有 2Y、活期存款基准利率用常量 0.35%
