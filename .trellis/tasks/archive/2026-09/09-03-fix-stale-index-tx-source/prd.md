# PRD: 中证红利等3指数改用腾讯源修复停更误判

## 背景

`config/benchmarks.yaml` 中 3 个指数配置的源为新浪 `stock_zh_index_daily`，但新浪对该代码的日线断更：
中证红利 `sh000922` 断于 2019-01-30、中证800成长 `sh000907` 断于 2016-06、中证800价值 `sh000908` 断于 2019-01。
fetcher 按末条数据 < end-10 天判定 stale 抛 `StaleIndexError`，导致这些指数永远走 fallback_chain（中证800/沪深300），
以它们为业绩基准的基金（如 210002 金鹰红利价值混合A）得到的是近似基准而非真实基准。

2026-09-03 实测：腾讯源 `stock_zh_index_daily_tx` 对 `sh000922` 返回全量数据（末条 2026-09-03 当日），
fetcher 该分支已存在（港股在用），返回列 date/open/close/high/low/amount，fetcher 仅取 date/close，兼容。

## 需求

1. `benchmarks.yaml` 中 中证红利/中证800成长/中证800价值 的 `source` 改为 `stock_zh_index_daily_tx`，
   并更新头注释（原「新浪停更…实际走 fallback」的说明不再成立）。
2. 测试覆盖：`stock_zh_index_daily_tx` 作为 A 股指数源时 `_fetch_index_daily` 正常工作（已有 hkHSI 用例可参照），
   且 fallback 链场景不受影响。
3. 真机验证：`sh000922` 拉取不再抛 `StaleIndexError`，`fetch_benchmark_tri("210002", ...)` source 返回 `fetched`（或不再走 fallback_chain）。

## 验收标准

- [x] yaml 3 处 source 改为 tx 源，注释同步
- [x] `python -m pytest tests/test_benchmark_fetcher.py -v` 全绿（29 passed，含 2 个新增）
- [x] 真机跑 `fetch_benchmark_tri("210002", ...)`：source=fetched（原 fallback_chain:sh000906），无 StaleIndexError 告警
