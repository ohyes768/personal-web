# 债基市场全量刷新 min_ret_3y 默认改 10%

## 目标

债基·市场 tab 的「全量刷新」对话框，把 `min_ret_3y` 默认值从当前与股基共用的 20% 改为 10%。
股基侧不动（保持 20%）。

两条 universe 走不同默认值的逻辑要显式拆开，避免「债基复用股基默认」这种隐性耦合。

## 范围

### 改动

1. **`apps/fund-select/src/lib/types.ts`**
   - 把 `DEFAULT_FULL_REFRESH_FILTERS` 拆成两个独立常量：
     - `DEFAULT_FULL_REFRESH_FILTERS_BOND`: `{ min_ret_3y: 10, min_size_yi: 5, min_mgr_exp: 5 }`
     - `DEFAULT_FULL_REFRESH_FILTERS_STOCK`: `{ min_ret_3y: 20, min_size_yi: 5, min_mgr_exp: 5 }`
   - 保留 `DEFAULT_FULL_REFRESH_FILTERS` 作为股基 alias（向后兼容老 import；deprecated 注释指向新常量）
   - `FullRefreshFilters` interface 不动

2. **`apps/fund-select/src/app/discovery-bond/page.tsx`**
   - 把第 30 行的 `DEFAULT_FULL_REFRESH_FILTERS` import 换成 `DEFAULT_FULL_REFRESH_FILTERS_BOND`
   - 第 47 行的 `useState<FullRefreshFilters>(DEFAULT_FULL_REFRESH_FILTERS)` 换为新常量

3. **`apps/fund-select/src/app/discovery-stock/page.tsx`**
   - 把第 29 行的 `DEFAULT_FULL_REFRESH_FILTERS` import 换成 `DEFAULT_FULL_REFRESH_FILTERS_STOCK`
   - 第 47 行的 `useState<FullRefreshFilters>(DEFAULT_FULL_REFRESH_FILTERS)` 换为新常量

### 同步清理（用户请求范围内）

4. **Trellis 脏任务清理**（4 个任务归档）：
   - `09-10-fund-table-type-chip`（已 commit `8f0fc76`，status=in_progress）
   - `09-10-qdii-reits-coarse-mapping`（已 commit `2a706ab`，status=in_progress）
   - `09-10-subtype-coverage-fix`（已 commit `587d739`，status=in_progress）
   - `09-09-market-size-xueqiu-first`（当前指针错位，已被本任务取代）

   归档前修正 `package` 字段（4 个全是 `backend/douyin-processor` → `backend/fund-select`），
   便于后续 sub-agent 按 package 取 spec 时不跑偏。

## 非范围（out of scope）

- 后端 `discovery_bond_full_refresh` 路由不变 — 接口继续接受 `Optional[float]`，
   默认值在客户端管
- `FullRefreshFilters` 接口字段不变
- **债基 L4 风险指标跳过**：risk_service.compute_risk_metrics 无差别算 6 指标，债基用不上。
   属于「债基全量刷新流程改造」级别，超出本任务范围，待后续单独立任务
- 3 个 09-10 任务的 PR（之前 commit 已包含功能）— 不补 PR，只归档

## 验收

| # | 验证项 | 验证方式 |
|---|---|---|
| A1 | 债基 tab 打开「全量刷新」对话框，`min_ret_3y` 默认显示 10 | devtools / 手动点开 |
| A2 | 股基 tab 打开「全量刷新」对话框，`min_ret_3y` 默认显示 20 | 同上 |
| A3 | 改完后 `apps/fund-select/src/lib/types.ts` 编译通过 | `pnpm -C apps/fund-select tsc --noEmit` |
| A4 | `apps/fund-select` lint 通过 | `pnpm -C apps/fund-select lint` |
| A5 | 4 个 Trellis 脏任务归档成功 | `task.py list` 不再出现这 4 个 in_progress 项 |
| A6 | 4 个任务的 task.json 中 `package` 字段已修正为 `backend/fund-select` | `cat` 归档目录里的 json |

## 设计决策

D1：保留 `DEFAULT_FULL_REFRESH_FILTERS` 作为 deprecated alias 指向股基常量。
   理由：不知道还有没有别的文件 import 它，删了等于删公共 API；alias + 注释标记即可。
   后续 grep 无人 import 后再删。

D2：只拆 `min_ret_3y`，`min_size_yi` 和 `min_mgr_exp` 仍共用。
   理由：用户只指定了 `min_ret_3y` 阈值差异；其他两个规模/经验字段，债基/股基采用同一标准合理。
   后续如需拆再拆。

## 关键文件

- `apps/fund-select/src/lib/types.ts:281` — 拆分点
- `apps/fund-select/src/app/discovery-bond/page.tsx:30,47` — 债基引用
- `apps/fund-select/src/app/discovery-stock/page.tsx:29,47` — 股基引用
- `.trellis/tasks/09-10-*` / `.trellis/tasks/09-09-market-size-xueqiu-first/` — 4 个待归档任务

## 后续待办（不在本任务内，标记给未来）

- **债基 L4 跳过**：全量刷新 6 阶段中 L4（风险指标 44 分钟）对债基全空跑，可在
  `market_full_pipeline.refresh_market_full_sync` 加 category 参数，对 `universe_filter`
  完全落在 bond subtype 的 code 跳过 risk_service 调用。债基全量刷新从 ~100 分钟 → ~56 分钟
- **债基 REITs 选项问题**：上一轮 review 提到的 P0 bug（勾 REITs = 筛选失效），
  推荐解法是直接删 `BOND_MARKET_TYPE_OPTIONS` 里的 REITs 选项
- **routes.py:294 注释漂移**："默认 = 10 个债券相关子类" 应改为 11（已补 混合型-偏债）