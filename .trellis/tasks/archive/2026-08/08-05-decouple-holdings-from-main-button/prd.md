# 股息率按钮状态机重构：拆分主按钮与指数徽章职责

## Background

2026-08-04 commit `423d2fe` 在主按钮 `needs_update` 临时加了 `or not holdings_complete`，用来解决"单指数刷残缺持仓时按钮可点"场景。**绑错了按钮**，带来两个问题：

1. **职责不清**：持仓缺一只指数 → 主按钮亮 + 徽章提示 → 用户不知道该点哪个
2. **prefilter 失真**：单指数刷后 `prefilter_stock_list_YYYY-MM.csv` 不更新，主按钮对比 1（`completed vs target`）间接偏差

前端已就绪：`apps/dividend/src/lib/hooks.ts:606 refreshIndexHoldings` 实时同步到 `indexResults`，`IndexStatusPopover` (`page.tsx:47`) 接 `holdingsStatus`。

## Goal

让"更新股息率"主按钮**只管"股票股息率算完了没"**（对比 1）；持仓覆盖度完全交给"指数状态徽章"+ 单指数重试入口。

业务侧新增要求：**单指数刷后必须 prefilter 重算成功，徽章才显示该指数完成 ✅**；否则仍标可重试。

## In Scope

1. 改 `backend/dividend-select/src/api/routes.py:1717`：删 `or not holdings_complete`
2. 抽 `_compute_prefilter_stock_list(holdings_df, fhps_df) -> list[str]` 公共函数（FR-3）
3. 改 `routes.py::refresh_dividend` + `main.py:CLI` 用抽出的函数（避免双实现口径漂移）
4. 改 `routes.py::refresh_single_index_holdings`：单指数刷成功后调用公共函数重算 + 写盘；接口响应扩字段
5. 改前端 `types.ts::IndexRefreshItem`：加 `prefilter_resynced` + `prefilter_error`
6. 改前端 `page.tsx::IndexStatusPopover::getRowState`：成功判定条件加严为 `success && prefilter_resynced`
7. 测试 + 端到端验证

## Out of Scope

- 前端 UI 整体改造
- 把 `fetcher.py:60/73` 的指数常量抽到 YAML/DB
- 多指数并发刷新改造
- prefilter 本身的"如何 ∩ fhps"逻辑改造（保留 `commit 3c1dce4` 的口径）

## User Scenarios

| 场景 | 期望行为 |
|---|---|
| 全量刷新成功 | 主按钮灰（"✅ 已是最新"）+ 所有指数徽章 ✅ |
| 股票计算有失败（completed < target） | 主按钮亮（"📥 待完成 X/Y"）+ 徽章按指数状态 |
| 持仓 CSV 缺一只指数 | 主按钮仅由对比 1 决定（不再"代管"）+ 徽章里缺的那只可单指数重试 |
| 单指数刷：持仓刷成功 + prefilter 重算成功 | 徽章 ✅ 显示完成 |
| 单指数刷：持仓刷成功 + prefilter 重算失败 | API 返回 `success=true, prefilter_resynced=false`；徽章不显示该指数 ✅，仍标可重试（错误信息"prefilter 同步失败"） |
| 单指数刷：持仓刷失败（旧逻辑） | API 返回 `success=false`；徽章显示 ✗ + 重试按钮 |

## Functional Requirements

### FR-1 移除主按钮的 holdings_complete 判断
- 改 `backend/dividend-select/src/api/routes.py:1717`
- 现状：`needs_update = completed_count < target_count or not holdings_complete`
- 改为：`needs_update = completed_count < target_count`
- `holdings_status` 字段**保留在 response 里**（仍给 `IndexStatusPopover` 用）
- 同步更新 docstring `routes.py:1601`（"或持仓指数覆盖不全"删掉）

### FR-2 单指数刷成功后本地重算 prefilter
- 位置：`refresh_single_index_holdings`（约 `routes.py:1943-1996`），`fetcher.replace_one_holdings(...)` 返回 `success=True` **之后**
- 重算步骤（不调 akshare）：
  1. 读 `data/{date_str}/红利指数持仓汇总_{date_str}.csv`（已被 replace_one_holdings 写好）
  2. 读 `data/fhps/fhps_{year_end}.csv`（如 `fhps_20251231.csv`，本地缓存）
  3. 主板 + 有 fhps 分红预案 + 在 8 指数并集内 → prefilter 集合
  4. 写盘 `data/{date_str}/prefilter_stock_list_{date_str}.csv`（单列股票代码）
- 失败处理：**`logger.error(...)` 不抛出**；把"prefilter 重算是否成功"作为新字段返回给前端

### FR-3 抽 `_persist_prefilter_stock_list` 写盘公共函数
- 位置：`backend/dividend-select/src/api/routes.py`（紧邻 refresh 入口）
- 签名：
  ```python
  def _persist_prefilter_stock_list(
      stock_items,        # Iterable[StockBasicInfo] 或 Iterable[str] 都接
      date_str: str,
  ) -> None:
      """把 prefilter 后的股票代码单列写盘。

      stock_items 可含 StockBasicInfo（含 .code）或纯 str。内部统一 zfill(6)，
      列类型 str，与汇总裁减口径一致。
      """
  ```
- 同时替换：
  - `routes.py::refresh_dividend`（约 1838-1841）现有 `pd.DataFrame + save_csv_data + log` 4 行
  - `main.py:166-168` 同款 3 行
- 不调 akshare；不调 fhps_fetcher
- **注意**：refresh_dividend / main.py 实际不"算 prefilter"——`fetcher.get_stock_list` 已经算好；这个函数只接手"写盘"动作。"单指数刷后的本地重算"涉及到读汇总 CSV + 读 fhps + 过滤，**那是另一条路径，本函数不抽**

### FR-4 后端响应扩字段
- 文件：`backend/dividend-select/src/api/models.py`（如无 models.py 就在 routes 内联响应模型）
- `IndexRefreshItem` 加两个字段：
  ```python
  prefilter_resynced: bool            # 单指数刷后 prefilter 重算是否成功
  prefilter_error: Optional[str]      # prefilter 失败原因（成功时为 None）
  ```
- `refresh_single_index_holdings` 改造：
  - 持仓刷成功 AND prefilter 重算成功 → `success=true, prefilter_resynced=true`
  - 持仓刷成功 AND prefilter 重算失败 → `success=true, prefilter_resynced=false, prefilter_error="..."`
  - 持仓刷失败 → `success=false`（`prefilter_resynced=false`，未尝试）

### FR-5 前端类型 + 渲染条件加严
- 改 `apps/dividend/src/lib/types.ts::IndexRefreshItem`：
  ```ts
  export interface IndexRefreshItem {
    code: string;
    name: string;
    success: boolean;
    constituents_count: number;
    error?: string | null;
    /** 单指数刷新后是否完成 prefilter 本地重算。徽章显示 ✅ 需要 true。 */
    prefilter_resynced: boolean;
    /** prefilter 重算失败原因 */
    prefilter_error?: string | null;
  }
  ```
- 改 `apps/dividend/src/app/page.tsx::IndexStatusPopover::getRowState`（约 line 74）：
  ```ts
  // before:
  return irItem.success ? { kind: 'refreshed_success', item: irItem }
                        : { kind: 'refreshed_failed', item: irItem };
  // after:
  return (irItem.success && irItem.prefilter_resynced)
    ? { kind: 'refreshed_success', item: irItem }
    : { kind: 'refreshed_failed', item: irItem };
  ```
- 顶部触发按钮配色（`btnClass`）自动跟随 `successCount` 变化，无需改
- 触发按钮的 `✓ 状态` 第 128 行也自动正确

## Acceptance Criteria

### AC-1 / FR-1
- [ ] `routes.py:1717` 已删除 `or not holdings_complete`
- [ ] `routes.py:1601` docstring 同步更新
- [ ] 单测 `test_status_needs_update_no_holdings_override`：
  - 准备：prefilter 144 只 + 持股汇总 CSV 存在但缺 1 个 `来源指数代码`
  - 操作：`GET /api/dividend/status`
  - 验收：`needs_update` 由 `completed_count < target_count` 单独决定（持仓缺指数不影响）

### AC-2 / FR-2 + FR-3
- [ ] 单测 `test_single_index_refresh_updates_prefilter`：
  - 准备：8 指数汇总 CSV（合计 144 只）+ fhps 缓存 + prefilter CSV 144 行
  - 操作：`POST /api/dividend/index-holdings/refresh` 带 `000922`
  - 验收：
    - prefilter CSV 行数 == 8 指数并集 ∩ fhps 过滤后股票数
    - response `prefilter_resynced=true, prefilter_error=null`
- [ ] 单测 `test_single_index_refresh_no_akshare_call`：mock `akshare.*` 任意入口 → FR-2 路径不抛 mock 错误（验证不调 akshare）
- [ ] 单测 `test_single_index_refresh_prefilter_failure`：
  - 准备：手动破坏汇总 CSV schema 或删除
  - 操作：调单指数刷
  - 验收：
    - response `success=true, prefilter_resynced=false, prefilter_error="..."`
    - 日志 ERROR 级别
    - prefilter CSV **未被破坏性覆盖**（如已存在则保留原内容）

### AC-3 / FR-3 抽公共函数
- [ ] `_compute_prefilter_stock_list(holdings_df, fhps_df)` 已实现
- [ ] `routes.py::refresh_dividend` 旧写盘逻辑替换为 `_compute_prefilter_stock_list(...) + save_csv_data(...)`
- [ ] `main.py` 旧逻辑同样替换
- [ ] 单测 `test_compute_prefilter_consistency`：同输入下函数输出 == 旧 `refresh_dividend` 实现输出（**先 stash 当前 main + routes 改动 + 跑测试 → 取消 stash → 跑新实现 → diff**）

### AC-4 / FR-4 + FR-5
- [ ] 后端 `IndexRefreshItem` 响应模型加 `prefilter_resynced` + `prefilter_error`
- [ ] 前端 `types.ts::IndexRefreshItem` 加同名字段
- [ ] 前端 `page.tsx::getRowState` 成功判定条件改为 `success && prefilter_resynced`
- [ ] 单测 `test_index_refresh_partial_state`：
  - mock 单指数刷接口返回 `success=true, prefilter_resynced=false`
  - 渲染 `IndexStatusPopover`（Jest + react-testing-library 或 smoke 测试）
  - 验收：该指数行显示 ✗ + "重试"按钮 + `prefilter_error` tooltip

### AC-5 回归
- [ ] `cd backend/dividend-select && python -m pytest tests/ -v` 全绿
- [ ] 端到端浏览器（手动）：
  - 场景 A：全量刷新成功 → 主按钮灰 + 所有徽章 ✅
  - 场景 B：单指数刷让 prefilter 重算失败 → 该指数徽章不显示 ✅、显示 ✗ + "重试"
  - 场景 C：单指数刷重试成功（prefilter 也成功）→ 徽章 ✅

## Constraints

- 改动主要在 `backend/dividend-select` 子模块（分支 `main`）
- 主仓库动作：子模块 commit+push → 主仓库 bump gitlink → commit+push
- 现有 `_is_refreshing` 全局并发锁必须保留
- 不引入新依赖

## Risks & 边界情况

| 风险 | 缓解 |
|---|---|
| 单指数刷后 prefilter 写盘但还没刷股息率 CSV | 主按钮正确变亮（completed<target），符合预期 |
| 单只指数 akshare 异常导致 `replace_one_holdings` 失败 | prefilter 不更新，主按钮对比 1 不变（不写脏数据） |
| fhps 缓存缺失（如从未 refresh 过） | 用 `commit 3c1dce4` 现有 fallback：prefilter 不写，target_count fallback 144 |
| 抽公共函数 → 改 `refresh_dividend` + `main.py` 触及刷新主路径 | **先 stash 改动跑基线测试**（按 memory `dividend-button-state.md` 的"改动前必须跑基线"原则） |
| 改前端 `getRowState` 影响线上徽章显示 | 必须在 AC-5 端到端实测三种场景 |
| 单指数刷在 `_is_refreshing=true` 时被拒（已有 409） | 不在本次改动范围 |

## Open Questions

无。FR-3 已拍 "抽公共函数"；"prefilter 重算成功才显示 ✅"已明确为 FR-4/FR-5 行为。

## Notes

- 待删的 1 天前补丁：`commit 423d2fe` (2026-08-04)
- prefilter 设计原则：`commit 3c1dce4` (2026-06-12)
- 预刷新基线原则：见 memory `MEMORY.md` 中 "改动前必须跑基线，否则无法区分「我改坏的」和「本来就坏的」"
- 前端现状：
  - `apps/dividend/src/lib/hooks.ts:606 refreshIndexHoldings`
  - `apps/dividend/src/app/page.tsx:47 IndexStatusPopover`
  - `apps/dividend/src/lib/types.ts:272 IndexRefreshItem`

## Acceptance 验证三件套

1. **代码可读**：路由/函数注释刷新（前/后 commit message 引用）
2. **测试覆盖**：AC-1 至 AC-5 全部单测 + pytest 全绿 + 浏览器 e2e 三种场景
3. **基线对照**：按 memory 规则，**改 `refresh_dividend` + `main.py` 前 stash 当前改动跑基线测试**，确保本次无回归

