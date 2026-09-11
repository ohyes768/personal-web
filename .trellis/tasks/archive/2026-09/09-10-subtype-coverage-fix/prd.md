# 补 SUBCLASS_TO_CATEGORY 缺失 subtype，让 UI 5 粗类别覆盖 universe 全集

## Goal

`apps/fund-select` 股基·市场（`/discovery-stock`）与债基·市场（`/discovery-bond`）tab 的「基金类型」5 个粗类别多选框当前**未覆盖全部 universe subtype**，导致主流基金无法通过 UI 筛选命中。本次补齐：

- 指数型-股票（5677 只，A 股 ETF / 指数增强主流）→ 归 `stock` universe，归「指数型」粗类别
- 混合型-偏股（5726 只）→ 归 `stock` universe，归「混合型」粗类别（股基侧）
- 混合型-偏债（1464 只）→ 归 `bond` universe，归「混合型」粗类别（债基侧）

QDII-商品（23 只）/ 商品（2 只）暂不进 universe，避免污染股票/债基 tab。

## Background

### 当前覆盖状况（修复前）

数据库里 `market_type='stock'` 的活跃基金共 16 个精确 subtype、12 个归类正确覆盖，4 个被遗漏：

| subtype | 数量 | SUBCLASS_TO_CATEGORY 当前归类 | 是否进 universe |
|---|---|---|---|
| 股票型 | 1140 | stock | ✅ |
| 混合型-平衡 | 74 | stock | ✅ |
| 混合型-绝对收益 | 38 | stock | ✅ |
| 混合型-灵活 | 2402 | stock | ✅ |
| **混合型-偏股** | **5726** | other（缺失） | ❌ |
| 指数型-海外股票 | 367 | stock | ✅ |
| 指数型-其他 | 70 | stock | ✅ |
| **指数型-股票** | **5677** | other（缺失） | ❌ |
| QDII-普通股票 | 89 | stock | ✅ |
| QDII-混合偏股 | 128 | stock | ✅ |
| QDII-混合灵活 | 29 | stock | ✅ |
| QDII-混合平衡 | 8 | stock | ✅ |
| QDII-FOF | 9 | stock | ✅ |
| QDII-REITs | 5 | stock | ✅ |
| Reits | 94 | stock | ✅ |
| REITs | 1 | stock | ✅ |
| QDII-商品 | 23 | other | ❌（暂不归） |
| 商品 | 2 | other | ❌（暂不归） |

`market_type='bond'` 的活跃基金共 12 个精确 subtype，1 个被遗漏：

| subtype | 数量 | SUBCLASS_TO_CATEGORY 当前归类 | 是否进 universe |
|---|---|---|---|
| 债券型-中短债 | 1181 | bond | ✅ |
| 债券型-混合一级 | 960 | bond | ✅ |
| 债券型-混合二级 | 1920 | bond | ✅ |
| 债券型-利率债 | 307 | bond | ✅ |
| 债券型-信用债 | 225 | bond | ✅ |
| 债券型-长债 | 2790 | bond | ✅ |
| 指数型-固收 | 677 | bond | ✅ |
| QDII-纯债 | 60 | bond | ✅ |
| QDII-混合债 | 23 | bond | ✅ |
| **混合型-偏债** | **1464** | other（缺失） | ❌ |

### 影响

- 用户在股基·市场 tab 勾「指数型」，预期找到 A 股指数 ETF，结果只返回 437 只（指数型-海外股票 367 + 指数型-其他 70），漏掉主流
- 用户勾「混合型」，漏掉 5726 只偏股混合基金
- 用户在债基·市场 tab 勾「混合型」，漏掉 1464 只偏债混合基金

## Requirements

### 后端改动（[market_subtype_map.py:20-58](backend/fund-select/src/data/market_subtype_map.py#L20)）

`SUBCLASS_TO_CATEGORY` 显式声明 3 个新映射：

```python
"指数型-股票": "stock",     # A 股 ETF / 指数增强（主流股基指数）
"混合型-偏股": "stock",     # 偏股混合基金（股票仓位 ≥60%）
"混合型-偏债": "bond",      # 偏债混合基金（股票仓位 ≤40%）
```

`DISCOVERY_STOCK_SUBTYPES` / `DISCOVERY_BOND_SUBTYPES` 由 `SUBCLASS_TO_CATEGORY` 自动重算，无需单独修改。

### 前端改动（[types.ts:212-226](apps/fund-select/src/lib/types.ts#L212)）

`COARSE_TO_SUBTYPES_STOCK`：
- `混合型` 数组追加 `'混合型-偏股'`
- `指数型` 数组追加 `'指数型-股票'`

`COARSE_TO_SUBTYPES_BOND`：
- `混合型` 数组追加 `'混合型-偏债'`

QDII / REITs / 纯债型 / 指数债等其他粗类别不动。

### 不变更

- 不动 `QDII-商品` / `商品` 的归类（仍归 "other"），本次不引入第 6 类「商品型」UI 框
- 不动 `MARKET_TYPE_OPTIONS` / `STOCK_MARKET_TYPE_OPTIONS` / `BOND_MARKET_TYPE_OPTIONS`（5 粗类别选项不动）
- 不动 `DEFAULT_FILTERS` / `STOCK_DEFAULT_FILTERS` / `DISCOVERY_*_DEFAULT_FILTERS` 默认 `market_types`（默认仍 5 类全选，行为不变）
- 不动 `SUBCLASS_TO_CATEGORY` 已声明的 14 个 stock + 10 个 bond 映射
- 不动 SQL 过滤逻辑 / `_screen` 函数
- 不动表格 UI（基金类型列展示 `market_subtype` 原值，不变）

## Acceptance Criteria

- [ ] [market_subtype_map.py:20-58](backend/fund-select/src/data/market_subtype_map.py#L20) 显式声明 `'指数型-股票': 'stock'`、`'混合型-偏股': 'stock'`、`'混合型-偏债': 'bond'`
- [ ] [types.ts:212-226](apps/fund-select/src/lib/types.ts#L212) 中 `COARSE_TO_SUBTYPES_STOCK['混合型']` 含 `'混合型-偏股'`；`COARSE_TO_SUBTYPES_STOCK['指数型']` 含 `'指数型-股票'`；`COARSE_TO_SUBTYPES_BOND['混合型']` 含 `'混合型-偏债'`
- [ ] discovery-stock 默认 5 粗类别全选 → 结果包含 `指数型-股票` / `混合型-偏股` 基金（任选一只已知 code 验证：嘉实中证 500ETF 联接A 000008 market_subtype='指数型-股票'）
- [ ] discovery-stock 勾「指数型」+ 不勾其他 → 结果包含 `指数型-股票 / 指数型-海外股票 / 指数型-其他` 三种 subtype，不再只有 437 只
- [ ] discovery-bond 默认 5 粗类别全选 → 结果包含 `混合型-偏债` 基金
- [ ] discovery-bond 勾「混合型」（债基侧，仅勾混合型）→ 结果包含 `混合型-偏债 / 债券型-混合债` 两种 subtype
- [ ] `QDII-商品` / `商品` 仍归 `other`，不进 stock/bond universe（保持现行为）
- [ ] 老 `stock` / `bond` tab 不受影响（不走 `market_types`）

## Verification Plan

1. **DB 实证**：
   ```bash
   sqlite3 data/funds.db "SELECT market_subtype, market_type FROM funds WHERE code='000008';"
   ```
   确认修复前后 `categorize('指数型-股票')` 返回 `'stock'`（已修）或 `'other'`（未修）。

2. **后端单测**：
   ```bash
   cd backend/fund-select && .venv/Scripts/python -m pytest tests/test_discovery_filter_service.py tests/test_market_universe_fetcher.py -v
   ```
   现有 21 + N 个用例应继续通过。

3. **新加单测覆盖回归点**（在 `test_discovery_filter_service.py` `TestScreenDiscoveryStock` / `TestScreenDiscoveryBond` 各加一条）：
   - `test_index_stock_included_when_index_coarse_selected`：seed `指数型-股票` 一只，勾「指数型」粗类别展开（含 `'指数型-股票'`）→ 命中
   - `test_partial_stock_included_when_mixed_coarse_selected`：seed `混合型-偏股` 一只，勾「混合型」粗类别展开（含 `'混合型-偏股'`）→ 命中
   - `test_partial_bond_included_when_mixed_coarse_selected_bond_tab`：seed `混合型-偏债` 一只，discovery-bond 勾「混合型」粗类别展开（含 `'混合型-偏债'`）→ 命中
   - `test_qdii_commodity_still_excluded_from_stock_universe`：seed `QDII-商品` / `商品` 各一只，discovery-stock 默认 universe → 不命中

## Risks

- **回归范围**：本次修改影响 universe 集合大小（stock universe 11.6k → 17.3k，bond universe 7.3k → 8.8k）。所有走 default universe 的接口（`screen_discovery_stock/bond`、`universe_stats`、全量 refresh `universe_filter`）行为都会变化。需要回归测试通过。
- **API 性能**：universe 变大 → SQL `IN (...)` 列表更长、`universe_stats` 计数变慢。当前 universe 已 ~10k 量级，影响可控。
- **前端全选默认行为**：5 粗类别默认全选时，结果集从 ~12k → ~22k，前端首屏 P95 可能受影响。本次不优化，留后续观察。

## Out of Scope

- 不动 `QDII-商品` / `商品` 归类（不引入「商品型」第 6 粗类别）
- 不动 UI 表格列展示
- 不动默认 `market_types` 5 类全选默认值
- 不动 `MARKET_TYPE_OPTIONS` 等粗类别 UI 选项定义
- 不动 `DEFAULT_FILTERS` 等默认筛选值