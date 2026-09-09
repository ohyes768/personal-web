# PRD: Pre-existing pytest 失败修复（peer_rank 契约 + cbond 源迁移）

## 大白话

`backend/fund-select/tests/` 有 6 个 pre-existing pytest 失败（与本次分页任务无关），但用户要求一并修复：

**5 个 peer_rank 测试**：d82928e commit（09-08-stock-fund-list-rank 任务）给 `_parse_peer_rank` 返回的 dict 加了 `rank` 键（{pct, total, **rank**}），但旧测试断言仍是 {pct, total}。生产代码已对，是测试没跟上契约更新。

**1 个 cbond 源测试**：akshare 升级到 1.18.39 后，`ak.bond_index_general_cbond` API 被移除（B1 修复 2026-09-04 引入）。**生产代码也用了这个 API**（refresh 时拉中债综合指数），所以这不只是测试问题，是真实回归——refresh 一旦命中就会 AttributeError。

## 范围

### 在范围内

1. 修复 `test_filter_service.py::TestParsePeerRank` 3 个 case 的断言（加 `rank` 键）
2. 修复 `test_stock_filter_service.py` 中 2 个 rank DTO 测试的断言（加 `rank` 键）
3. 把生产代码 `benchmark_fetcher.py` 的 `ak.bond_index_general_cbond(...)` 替换为 `ak.bond_new_composite_index_cbond()`（验证过：6174 行数据，日期对齐正确，无 B1 错位 bug）
4. 更新 `config/benchmarks.yaml` 的 source 字段 + 注释
5. 更新 `test_benchmark_fetcher.py` 的 patch 目标 + 注释
6. 更新 `contracts.md` 的 B1 段落

### 不在范围内

- 重新评估整体 akshare 版本兼容性（其它 akshare API 调用暂不动）
- 重跑 refresh 实测（本次不实际触发 refresh，只验证代码改动后的接口调用语义）
- 前端 / 其它后端

## 验收标准

### 后端 pytest

1. `pytest backend/fund-select/tests/test_filter_service.py::TestParsePeerRank -v` → 5/5 PASS（3 个原本失败的 + 2 个原本就 pass 的）
2. `pytest backend/fund-select/tests/test_stock_filter_service.py -v` → 全部 PASS（含 `test_screen_stock_dto_has_rank_keys_with_full_data` 和 `test_screen_stock_dto_rank_partial`）
3. `pytest backend/fund-select/tests/test_benchmark_fetcher.py -v` → 全部 PASS（含 `TestFetchIndexDaily::test_cbond_source_dates_kept_as_is`）
4. `pytest backend/fund-select/tests/ -v` 全量 → 之前 5+1=6 个失败全部变 PASS，无新增失败
5. cbond 源迁移后**不能引入新 B1 bug**：周五/周六调休交易日保留、无周日错位行（与原 B1 测试断言一致）

### 文档

6. `contracts.md` 的 B1 段落更新：
   - 注明 `bond_new_composite_index_cbond` 是当前源（akshare 1.18.39 起）
   - 实证数据：6174 行 / Sun=11 / Sat=9 调休交易日
   - 删除对 `bond_index_general_cbond` 的引用（或改为历史说明）

### 不破坏的约束

7. 生产 refresh 路径中调用 cbond 源不再 AttributeError（grep 验证：benchmark_fetcher.py 中无 `ak.bond_index_general_cbond` 残留）
8. yaml config 中相关条目 source 字段已更新

## 风险

| 风险 | 缓解 |
|---|---|
| `bond_new_composite_index_cbond` 实际上有 B1 同款 bug | 已实证：2024-10-11 周五、10-12 周六调休、10-14 周一日期正确；近 3 年 weekday 分布 Sun=11 / Sat=9 / Mon-Fri=144-149（无 B1 错位的 Sun=142 异常） |
| 迁移后某些 yaml 配置的 source 字段仍指向旧名 | grep 验证 yaml 中所有 cbond 相关 source |
| 测试断言写错（peer_rank 契约正确形式不止 rank 加 key） | 跑全量 pytest 兜底；RankPercentile DTO 类型已确认 `{pct, total, rank}`（types.ts 142） |

## 不在本次范围（后续可处理）

- `apps/fund-select` 缺 ESLint 配置（之前 implement/check 子代理提过）
- 其它潜在的 akshare 版本漂移（本次仅针对本次失败的 1 个 API）
