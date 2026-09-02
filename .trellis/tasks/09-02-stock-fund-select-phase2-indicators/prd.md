# phase2-B 指标计算：risk_service + 前端展示列

## Goal

消费 phase2-A 交付的 `fund_benchmark`（TRI 序列）与 `risk_free_rate`（国债 2Y 日频），实现 6 个风险/超额指标的计算、入库、API 输出与前端展示：

1. **Sharpe**（夏普比率）
2. **IR**（信息比率）
3. **选股能力 α**（T-M 回归截距，年化）
4. **择时能力 γ**（T-M 二次项系数）
5. **选股 α IR** = `α / σ_residual × √252`
6. **超额收益**（基金 vs 基准，近 3 年）

## 前置依赖（必须先完成）

- [ ] `09-02-stock-fund-select-phase2-infra`（A）已 archive
- [ ] DB 存在 `fund_benchmark`（142 只 tri 非 NULL）与 `risk_free_rate`（8000+ 行）数据
- [ ] `fetch_nav`（已有）可拉基金单位净值序列

**A 未完成前本 task 不开 design / implement / start**——指标窗口、对齐规则等设计细节依赖 A 的实际数据形态。

## Requirements

### 1. `src/services/risk_service.py`（新建）

计算窗口统一**近 3 年**（与第一阶段 dd_3y 口径一致）；日频收益；`√252` 年化。

| 指标 | 公式 | 输入 |
|---|---|---|
| Sharpe | `(R_p − R_f).mean() / (R_p − R_f).std() × √252` | 基金日收益 + risk_free 日频（年化小数÷252 折日） |
| IR | `(R_p − R_b).mean() / (R_p − R_b).std() × √252` | 基金日收益 + 基准 TRI 日收益 |
| 超额收益 | `∏(1+R_p) − ∏(1+R_b)`（3 年累计） | 同上 |
| 选股 α | T-M 回归 `R_p − R_f = α + β(R_b − R_f) + γ(R_b − R_f)² + ε` 的 α，年化（×252） | 同上 |
| 择时 γ | 同上回归的 γ | 同上 |
| 选股 α IR | `α / σ_ε × √252` | 回归残差标准差 |

**对齐规则**：基金净值日 ∩ 基准交易日内连接；risk_free 按日 ffill。

**容错**：
- 基准 tri=NULL（968157）→ 全部 6 指标 NULL，前端显示 "—"
- 样本 < 250 个交易日 → 指标 NULL（不足 1 年数据无统计意义）
- std=0 / 回归退化 → 指标 NULL，WARN 日志

### 2. `FundRiskMetrics` 表（新 ORM + alembic 迁移）

一行一基金：code 主键 + sharpe / ir / alpha / gamma / alpha_ir / excess_ret_3y + as_of_date + updated_at。

### 3. Refresh 接入

- `refresh_stock_funds_sync` 末尾追加 risk 计算步骤（读 DB nav + benchmark + risk_free，纯计算无网络请求）
- 不动债基路径

### 4. API

- `GET /api/funds/stock` 响应追加 6 个字段（复用现有路由，扩展 serializer）

### 5. 前端（apps/fund-select）

- `/funds/stock` 表格追加 6 列：夏普 / IR / 选股α / 择时γ / α-IR / 超额收益(3y)
- 排序按钮可用；导出 CSV 包含新列；空值 "—"
- 不动债基页面

## Acceptance Criteria

- [ ] `risk_service` 单测：手工构造已知收益序列，断言各指标数值正确（容差 1e-6）
- [ ] 单测覆盖容错分支：基准 NULL / 样本不足 / std=0 → 指标 NULL 不抛异常
- [ ] T-M 回归单测：构造精确线性/二次关系序列，断言 α γ 恢复
- [ ] `uv run pytest tests/ -v` 全过（含 A 的测试）
- [ ] 全量 143 只计算一次入库；142 只 6 指标非 NULL，968157 全 NULL
- [ ] `GET /api/funds/stock` 返回 6 个新字段
- [ ] 前端 `/funds/stock` 显示 6 列 + 排序 + CSV 导出
- [ ] `pnpm exec tsc --noEmit` 0 错；`pnpm build` 过
- [ ] 债基页面 `/funds` 零变化

## Notes

- design.md / implement.md 在 A archive 后撰写（依赖 A 的真实数据形态）
- 数值格式：Sharpe / IR / α-IR 保留 2 位小数；α / γ / 超额收益百分比保留 2 位
- 注：实际代码路径 backend/fund-select + apps/fund-select（package 注册表暂不支持，沿用 douyin-processor 占位）
