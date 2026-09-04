# 基准 TRI 合成修复：价格对齐替代收益 ffill（B2）

## 背景

2026-09-03 指标 review 发现：`benchmark_fetcher.fetch_benchmark_tri` 在混合交易日历（A股 + 港股 + 美股 + 错位中债）场景下，对**收益率序列**做 `ffill()`——某成分不交易的日期，该成分**前一天的日收益被重复计入**，3 年累积使基准系统性失真。

实测（004316 前海开源沪港深裕鑫A，基准=沪深300×50%+恒生×20%+中债×30%，2026-09-03 全量刷新后数据）：

| 口径 | 3y 基准涨幅 | excess_3y |
|---|---|---|
| 正确合成（价格对齐） | +21.77% | −15.60% |
| 库中（收益 ffill） | +35.31% | −13.44% |

基准被虚高 13.54pp，页面 excess_3y 高估 ~2.2pp。40 只非 QDII 基金基准含混合日历（周末行），全部受影响。

## Goal

`fetch_benchmark_tri` 的多成分合成改为**价格对齐**：并集日历上对成分**价格** ffill 后统一重算日收益，缺失交易日贡献收益 0（价格不变），不再复制前日收益。

## Requirements

1. `fetch_benchmark_tri` 内：成分序列从"日收益"改为"收盘价"；并集日历 `reindex + ffill` 价格；`pct_change` 得日收益；首位 NaN（成分未上市）行 `dropna` 裁掉——基准在任一成分有价格前无定义。
2. deposit_floor 成分处理不变（常数日收益，作用于全部并集日期）。
3. 权重归一化（`w / total_w`）、TRI 参考日 1000、`source` 标记（fetched / partial:fallback / fallback_chain）语义全部不变。
4. `_fetch_index_daily`、`_resolve`、fallback 链路、stale 检测不动（`_fallback_chain_tri` 仍可用 `return` 列——单指数无对齐问题）。
5. 单一日历基准（全部成分同源同日历，占多数）结果应与现算法一致（回归保障）。

## 边界（不在本任务内）

- **B1**（中债源日期整体 −1 天，周五数据标成周日）：独立任务。修复 B2 后基准不再双计收益，但中债成分的收益仍落在错位日期上。
- **B3**（unknown 成分被 fallback 静默替换、32 只非 QDII 错配）：独立任务。
- QDII skip、risk_service 口径（fix-risk-adjusted-nav，另有未提交工作区改动）：不碰。

## Acceptance Criteria

- [x] 单测：构造两成分不同日历（如 A 周一/三/五、B 周二/四），断言 B 缺席日 B 的收益贡献为 0，TRI 只含 A 当日收益 × 权重（不再双计）
- [x] 单测：成分历史起点晚于窗口起点时，并集起点被裁到最晚成分首个交易日
- [x] 单测（回归）：全成分同一日历的基准，新旧算法 TRI 完全一致
- [x] `uv run pytest tests/ -v` 全过（130 passed）
- [x] 定向重刷 004316（benchmark+risk）：TRI 3y 涨幅 +22.75% ≈ 独立复算 +21.77%（残差 0.95pp 为 B1 中债日期错位，在容忍内）。注：excess_3y 预期值 −15.6% 是 PRD 撰写时用旧基金侧口径 + TRI 端点口径混算的 flawed 预期——指标按 inner-join 日历计算，实际 −11.41%（基准端修复 +2.03pp 与 join 日历下双计消除量一致，归因详见 check 报告）
- [x] ~~全量重建 142 只~~ → descoped 后已被后续任务实际覆盖完成：`09-04-benchmark-yaml-coverage`（28b52a4，收录扩充后全库 142 只 benchmark+risk 重刷）与 `09-04-fix-bond-index-date-shift`（fe8c992，中债换源后再重刷 42 只中债成分基金）。当前库内数据 = B1+B2+B3 三重修复后的最终状态，无需再重建。
> 归档补注（2026-09-04）：B1 已由 fix-bond-index-date-shift 修复（换源，0 差值实证）；B3 已由 benchmark-yaml-coverage 修复（顶替 32→0）。本 PRD「边界」段引用的 B1/B3 开放状态均已关闭。
