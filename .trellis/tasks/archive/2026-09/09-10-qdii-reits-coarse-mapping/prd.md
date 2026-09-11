# QDII-REITs 粗类别归到 QDII，避免不勾 QDII 仍出现 QDII 海外 REITs

## Goal

修复股基·市场（`/funds/discovery-stock`）tab「基金类型」多选 bug：用户取消勾选「QDII」粗类别后，结果列表仍出现 5 只名字带「(QDII)」的海外 REITs 基金（鹏华美国房地产、嘉实全球房地产、诺安全球收益不动产等），体验上违反用户直觉。

## Background

### 根因

[apps/fund-select/src/lib/types.ts:212-218](apps/fund-select/src/lib/types.ts#L212) 的 `COARSE_TO_SUBTYPES_STOCK` 把 `QDII-REITs` 归到了 **REITs** 粗类别下：

```typescript
'QDII': ['QDII-普通股票', 'QDII-混合偏股', 'QDII-混合灵活', 'QDII-混合平衡', 'QDII-FOF'],
'REITs': ['Reits', 'REITs', 'QDII-REITs'],   // ← QDII-REITs 归这里
```

后端 SQL 是精确枚举 `Fund.market_subtype IN (...)`。当用户取消勾选「QDII」但保留「REITs」时，`market_type` 查询串里依然包含 `QDII-REITs`，所以 5 只 QDII-REITs 基金仍然命中。它们基金名字都带「(QDII)」字样（鹏华美国房地产(QDII) 等），用户看到结果第一反应是「我明明没勾 QDII 怎么还有 QDII 基金」。

### 为什么 QDII-REITs 当前归 REITs

`market_subtype_map.py` 里 `QDII-REITs` 被归为 `stock` universe（与 Reits/REITs 同组，不归 `other`），目的是让股基·市场 tab 默认 universe 能扫到海外 REIT 基金。前端粗类别顺势把它放到 REITs 下，但跨界的命名（QDII × REITs）和用户对「QDII 粗类别」的直觉不一致——「QDII」粗类别应当包含所有 QDII 系列，无论底层标的是股票还是 REIT。

### 实证

直接对 DB 用 `market_subtype IN ('股票型','混合型-平衡','混合型-绝对收益','混合型-灵活','指数型-海外股票','指数型-其他','Reits','REITs','QDII-REITs')` 查询（不勾 QDII 但勾 REITs），命中 5 只 QDII 基金：

| code | name | market_subtype |
|---|---|---|
| 006283 | 鹏华美国房地产美元现汇 | QDII-REITs |
| 027794 | 诺安全球收益不动产(QDII)C | QDII-REITs |
| 070031 | 嘉实全球房地产(QDII) | QDII-REITs |
| 206011 | 鹏华美国房地产(QDII) | QDII-REITs |
| 320017 | 诺安全球收益不动产(QDII)A | QDII-REITs |

## Requirements

### 行为变更

`COARSE_TO_SUBTYPES_STOCK` 中：
- `QDII` 粗类别新增 `'QDII-REITs'`
- `REITs` 粗类别移除 `'QDII-REITs'`，保留 `['Reits', 'REITs']`

修改后：
- **不勾 QDII**：所有 QDII 系列（包括 QDII-REITs）都不出现
- **勾 QDII + 不勾 REITs**：QDII-REITs 出现（符合"QDII 大类"语义）
- **不勾 QDII + 不勾 REITs**：QDII-REITs 不出现
- **勾 QDII + 勾 REITs**：QDII-REITs 出现（去重后只 1 份）

### 不变更

- 不动 `market_subtype_map.py` 的 `SUBCLASS_TO_CATEGORY`（QDII-REITs 仍归 `stock` universe）
- 不动后端 `filter_service.py` 任何过滤条件
- 不动 `DISCOVERY_STOCK_SUBTYPES`（默认 universe 仍含 QDII-REITs）
- 不动 `BOND_MARKET_TYPE_OPTIONS` 与 `COARSE_TO_SUBTYPES_BOND`（QDII 债基不受影响）
- 不动表格 UI 渲染（market_subtype 原值展示）

## Acceptance Criteria

- [ ] [types.ts:212-218](apps/fund-select/src/lib/types.ts#L212) 中 `QDII` 数组新增 `'QDII-REITs'`；`REITs` 数组移除 `'QDII-REITs'`
- [ ] `discovery-stock` 默认 `market_types`（5 个粗类别全选）下，结果集仍包含 QDII-REITs（去重后只出现 1 份）
- [ ] `discovery-stock` 取消勾选 QDII 粗类别后，结果集**不再**包含任何 `market_subtype` 以 `QDII` 开头的基金（含 QDII-REITs、QDII-普通股票 等）
- [ ] `discovery-stock` 仅勾选 QDII（不勾 REITs）时，QDII-REITs 仍能命中
- [ ] `discovery-bond` 不受影响（`COARSE_TO_SUBTYPES_BOND` 中无 QDII-REITs 改动）
- [ ] 老 `stock` / `bond` tab 不受影响（不走 `market_types`）

## Verification Plan

1. **代码改完后跑现成单测**：
   ```bash
   cd backend/fund-select && .venv/Scripts/python -m pytest tests/test_discovery_filter_service.py -v
   ```
   `TestScreenDiscoveryStock` 现有用例（默认 universe、custom subtype 缩窄）应继续通过。

2. **新加单测覆盖回归点**：
   - 在 `test_discovery_filter_service.py` `TestScreenDiscoveryStock` 加一条 `test_qdii_coarse_excludes_qdii_reits`：seed 一只 `QDII-REITs` 基金，传 `market_types=['股票型']`（不含 QDII），断言它**不在**结果里；再传 `market_types=['股票型','QDII']`，断言它在结果里。

3. **DB 实证**：用 sqlite3 直接验证 `market_subtype IN (expanded_when_qdii_unchecked)` 命中数为 0（参考 Background 的查询脚本）。

## Risks

- **产品语义边界 case**：`QDII-REITs` 兼具 QDII + REITs 两个属性。修改后不勾 REITs 但勾 QDII 也能看到 QDII-REITs，可能让部分用户疑惑「我没勾 REITs 怎么有 REITs 基金」。可在 UI 上接受（QDII 包含所有 QDII 系列是更通用的语义），也可后续加 chip 标记。本次只改映射，UI 不动。
- **缓存**：前端 Next.js dev 缓存可能需清，测试时手动 hard reload 一次。

## Out of Scope

- 不动后端 `market_subtype` 字段归类（`SUBCLASS_TO_CATEGORY`）
- 不动 `DISCOVERY_STOCK_SUBTYPES` 默认 universe
- 不改 UI 文案 / chip 标记
- 不动债基 tab (`COARSE_TO_SUBTYPES_BOND`)