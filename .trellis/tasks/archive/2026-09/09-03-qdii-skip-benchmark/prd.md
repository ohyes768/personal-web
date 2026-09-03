# PRD：QDII 基金跳过业绩基准计算

## 背景

股票宇宙（143 只）刷新时，QDII 基金的业绩比较基准公式（MSCI ACWI、标普全球高端消费品、人民币计价的纳斯达克100 等）大多无法解析或无免费数据源，每次刷新：

1. 打大量 WARNING（「公式整体不可解析」）；
2. 走 fallback_chain（中证800）合成错误基准，算出的 IR / 选股α / 超额3y 等是**误导性数字**。

用户决策（2026-09-03）：QDII 先不算基准，界面显示 `-`。

## 需求

`_refresh_fund_benchmarks`（backend/fund-select/src/scheduler/tasks.py）对 QDII 基金跳过基准 TRI 合成：

- 判定条件与 `filter_service._screen` 的 exclude_qdii 一致：`fund_type` 以 `QDII` 开头 **或** 等于 `互认基金`；
- 跳过 `fetch_benchmark_tri`，直接写一行 `FundBenchmark(tri=None, source="skipped:qdii")`（沿用 delete + insert 幂等模式）；
- 下游 `refresh_fund_risks` 读到 tri=NULL 后自动只算 sharpe，`ir / alpha / gamma / alpha_ir / excess_3y` 保持 None。

## 明确不做（out of scope）

- sh000922 / sh000908 停更换源（中证红利/中证800价值，A股基金，另一问题）；
- MSCI / 标普全球别名映射；
- `_MUL_MAP` 英文 x 误当乘号的解析 bug；
- 前端改动（`fmt` 已对 null 渲染 `-`，排序 None 恒排尾部，零改动）。

## 验收标准

1. QDII/互认基金刷新后 `fund_benchmark` 只有一行 `tri=NULL, source='skipped:qdii'`，日志无「公式整体不可解析」类告警（对该批基金）；
2. 该批基金 `fund_risk_metrics`：`sharpe` 有值（若净值样本足够），其余 5 指标为 NULL；
3. 非_QDII 基金基准计算行为不变；
4. `python -m pytest tests/ -v` 全绿，含新增跳过逻辑测试。

## 验证方式

```bash
cd backend/fund-select && python -m pytest tests/ -v
```

集成验证：刷新股票宇宙后查 `fund_benchmark.source='skipped:qdii'` 行数 = QDII 基金数；前端股票 tab（不勾 exclude_qdii）QDII 行 5 列显示 `-`。
