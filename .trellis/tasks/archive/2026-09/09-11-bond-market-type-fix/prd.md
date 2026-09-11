# 债基·市场 tab 类型筛选修正

## 背景

改完股基·市场 tab 后切到债基·市场 tab，review 发现两个缺陷。根因相同：股基侧的类型映射改动（commit `8f0fc76` / `587d739` / `2a706ab`）只在股基语境下验证过，债基侧的差异没被覆盖。

## 问题

### P0 — 勾「REITs」导致筛选静默失效，返回全量债基

调用链（四段均已核对原文）：

1. `apps/fund-select/src/lib/types.ts:227` — `COARSE_TO_SUBTYPES_BOND['REITs'] = []`
2. `apps/fund-select/src/lib/api.ts:33` — `if (expanded.length > 0) params.set('market_type', ...)`，空展开**静默不传参**
3. `backend/fund-select/src/api/routes.py:268` — `_parse_market_types(None)` → `None`
4. `backend/fund-select/src/services/filter_service.py:158` — `market_types is None` → 落回 `DEFAULT_DISCOVERY_UNIVERSE`，返回全部 11 个债基子类

用户只勾 REITs，期望 0 只，实际拿到**全部债基**。filter 退化成 no-filter，且无任何提示。

股基侧 5 个粗类别映射均非空，不触发此路径。

后端 `SUBCLASS_TO_CATEGORY` 已明确把 `Reits` / `REITs` / `QDII-REITs` 全归到 `stock`，**债基 universe 结构上不含 REITs**，所以该选项本就是死选项。

### P1 — chip 文案与筛选器文案不一致（仅债基侧）

`FundTable.tsx` 的 `TypeCell` 调 `resolveCoarseLabel()` 返回映射表的 **key**，而债基筛选器 `BOND_MARKET_TYPE_OPTIONS` 展示的是 **label**：

| market_subtype | 筛选器显示 | 表格 chip 显示 |
|---|---|---|
| 混合型-偏债 | 混合债基 | 混合型 |
| 指数型-固收 | 指数债 | 指数型 |
| QDII-纯债 | QDII 债 | QDII |

股基侧 value === label，天然一致，所以上个任务没暴露。

附带根因：`types.ts:247` 的 `resolveCoarseLabel` 不区分 tab，写死 `STOCK ?? BOND` 优先级。当前两表 key 无交集尚未出错，但任何一方补键都会撞。

## 方案

P0 取方案 A：**删除债基侧 REITs 死选项**，语义诚实（债基 universe 本就没有），零回归面。

P1 顺 `FundTable` 已有的 tab 区分 prop 约定（`showBondColumns` / `showRiskColumns` / `ddBarCapPct`），给 `resolveCoarseLabel` 补显式 tab 参数。

## 改动清单

| 文件 | 改动 |
|---|---|
| `types.ts:193-199` | `BOND_MARKET_TYPE_OPTIONS` 删除 REITs 项（剩 4 个粗类别） |
| `types.ts:227` | `COARSE_TO_SUBTYPES_BOND` 删除 `'REITs': []` 死条目 |
| `types.ts:244-248` | `resolveCoarseLabel(subtype, kind?)` 增加可选 `kind: 'stock' \| 'bond'`；命中时返回对应 OPTIONS 的 **label**；`kind` 缺省时保持现有 `STOCK ?? BOND` fallback |
| `types.ts` | 新增从 `*_MARKET_TYPE_OPTIONS` derive 的 value→label 映射，**不硬编码第二份文案**（避免漂移） |
| `FundTable.tsx:12-30` | props 增加 `marketKind?: 'stock' \| 'bond'` |
| `FundTable.tsx:61-75` | `TypeCell` 接收并透传 `kind` |
| `FundTable.tsx:181` | 调用点传 `kind` |
| `discovery-bond/page.tsx:110` | 传 `marketKind="bond"` |
| `discovery-stock/page.tsx` | 传 `marketKind="stock"` |

## 不做

- 不改 `buildQuery` 的空展开逻辑（那是方案 C，动股基/债基共享代码，回归面最大）
- 不改后端任何文件（后端行为正确，问题全在前端映射层）
- 不动 `/bond`、`/stock` 老 tab：`marketKind` 为 optional，缺省行为与现状逐字节一致
- 不改 `STOCK_MARKET_TYPE_OPTIONS`（股基侧无此问题）

## 验收标准

1. 债基·市场 tab 基金类型筛选器只出现 4 个选项：纯债型 / 混合债基 / 指数债 / QDII 债，**无 REITs**
2. 债基 tab 任意粗类别组合勾选后，`market_type` 查询参数**必然非空**（不存在展开为空数组的路径）— 由 1 结构性保证
3. 债基 tab 表格 chip 文案与筛选器 label 逐字一致（`混合型-偏债` → chip 显示「混合债基」）
4. 股基·市场 tab 筛选器选项、chip 文案、返回条数与改动前完全一致（回归）
5. `/bond`、`/stock` 老 tab 类型列渲染与改动前一致（回归）
6. `pnpm lint` 与 `pnpm build` 通过

## 附带清理（非代码，Phase 3 处理）

- archive 三个已 commit 但仍 `in_progress` 的任务：`09-10-fund-table-type-chip`、`09-10-qdii-reits-coarse-mapping`、`09-10-subtype-coverage-fix`
- 修正上述任务 + 本任务的 `package` 字段：`backend/douyin-processor` → `backend/fund-select`（模板默认值未改，sub-agent 据此取 spec 会读到无关包）
- `backend/fund-select/scripts/_*.py` 4 个未跟踪临时脚本 — **不动**（用户裁决 2026-09-11）。未跟踪状态已等价于「本地保留、不进仓库」，加 .gitignore 属多余改动
- `routes.py:294` 文档漂移（注释写「10 个债券相关子类」，补 `混合型-偏债` 后实为 11 个）— 单行注释，可顺手改
