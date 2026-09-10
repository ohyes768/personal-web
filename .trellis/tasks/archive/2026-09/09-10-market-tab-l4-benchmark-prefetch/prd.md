# market tab L4 risk refresh 补 benchmark 写入

## 大白话

市场 tab 算风险指标（夏普/IR/α）的时候，**漏跑了一步**——本来应该先拉每只基金的"业绩比较基准"指数（比如沪深 300、中证 500 这种），存到 `fund_benchmark` 表，再拿这张表去算风险指标。但市场 tab 直接跳过了第一步，导致 `fund_benchmark` 表对市场 tab 的基金是空的，IR 算不出来。

线上日志佐证：

```
2026-09-10 10:02:27 [INFO] fund-select.risk_service: [risk 442/458] 519770: ir=None (no fund_benchmark row → 公式可能 FETCH ERR)
```

股票 tab 没这个问题，因为它的入口 `refresh_configured_funds_sync` 调过 `_refresh_fund_benchmarks`（写在 [scheduler/tasks.py:173](backend/fund-select/src/scheduler/tasks.py:173)）。

仅市场 tab 覆盖的 458 只里有约 442 只报这条日志，说明问题就是市场 tab。

## 需求

### R1 修复架构

把 `_refresh_fund_benchmarks`（目前只在 stock tab 入口用）变成两个 tab 共用的公共 service，让市场 tab 跑 risk refresh 前先调它。

具体改动：
1. **新建** `backend/fund-select/src/services/benchmark_refresh.py`：把 `_refresh_fund_benchmarks` 函数（[tasks.py:173-222](backend/fund-select/src/scheduler/tasks.py:173)）移过来，改名 `refresh`，去掉前置下划线。
2. **改** `backend/fund-select/src/services/market_risk_refresh.py`：在 `refresh(session, codes)` 里、`refresh_fund_risks(session, codes)` 之前，调一次 `benchmark_refresh.refresh(session, codes)`。错误合并到 errors 列表。
3. **改** `backend/fund-select/src/scheduler/tasks.py`：`_refresh_fund_benchmarks` 函数删掉，import 新的 `benchmark_refresh.refresh` 替代，保持 stock tab 行为不变。

### R2 测试

`tests/test_risk_refresh.py` 新增：
- `test_market_risk_refresh_writes_benchmark_first`：mock `_refresh_fund_benchmarks`（或新的 `benchmark_refresh.refresh`），验证 market_risk_refresh.refresh 调用顺序：先 benchmark 再 risk。
- `test_market_risk_refresh_propagates_benchmark_errors`：benchmark refresh 报错的基金被加进 errors 列表，不阻塞后续。
- `test_market_risk_refresh_skips_benchmark_when_codes_empty`：codes 为空时 benchmark 不被调（避免空转）。

现有 `tests/test_risk_refresh.py` 不应受影响。

### R3 验收

- 跑 `market_full_pipeline.refresh_market_full_sync` 后，`fund_benchmark` 表对市场 tab 覆盖的所有基金**至少有一行**（QDII 跳过行 `tri=None, source=skipped:qdii` 或 unavailable 行 `tri=None, source=unavailable:*`，或真实指数数据行）。
- `risk_service.refresh_fund_risks` 不再打出 `no fund_benchmark row` 日志（这一支走 `source=*` 分支）。
- `tests/test_risk_refresh.py` 全过；`tests/test_market_full_pipeline.py`、`tests/test_filter_service.py`、`tests/test_api.py` 全部回归通过。

## 不做的事

- 不改 risk_service.refresh_fund_risks 的内部逻辑（让它自己 fetch benchmark 会破坏"纯计算函数"边界）。
- 不合并 stock tab / market tab 入口（任务边界外）。
- 不动 fund_benchmark 表 schema 或 source 字段取值。
- 不删 QDII 跳过行的写入逻辑（QDII/互认基金本来就该跳过基准合成）。
