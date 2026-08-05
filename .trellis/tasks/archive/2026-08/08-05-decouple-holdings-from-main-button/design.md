# Design: 股息率按钮状态机重构

## Boundaries

### 后端（`backend/dividend-select`，分支 `main`）
| 文件 | 改动范围 |
|---|---|
| `src/api/routes.py` | (a) line 1717 删 `or not holdings_complete`；(b) `refresh_dividend` 改用新抽函数；(c) `refresh_single_index_holdings` 加 prefilter 重算 + 改响应 |
| `src/api/models.py` 或 `routes.py` 内联 | `IndexRefreshItem` 加 `prefilter_resynced: bool` + `prefilter_error: Optional[str]` |
| `main.py` | CLI 路径改用新抽函数 |
| `tests/` | 新增 / 修改 4 个单测（AC-1 / AC-2 / AC-3 / AC-4 见 PRD） |

### 前端（`apps/dividend`）
| 文件 | 改动范围 |
|---|---|
| `src/lib/types.ts` | `IndexRefreshItem` 加 2 字段（line 272） |
| `src/app/page.tsx` | `IndexStatusPopover::getRowState` 成功判定条件加严（line 74） |

**不在改动范围**：
- `useDataUpdate` hook 内部逻辑（已能透传新字段，不需要改）
- 主按钮（`page.tsx:523`）的 disabled 条件（FR-1 改后端后自动正确）
- `useRefreshPrice`、`useStockInfo`、`useDividendData` 等其他 hook

## Contracts

### C-1 后端响应：`IndexRefreshItem`
```python
# 字段顺序：先原有字段，再新字段（向后兼容追加）
{
  "code": "000922",
  "name": "中证红利",
  "success": true,
  "constituents_count": 50,
  "error": null,
  "prefilter_resynced": true,        # NEW: prefilter 重算成功
  "prefilter_error": null,           # NEW: prefilter 错误信息
}
```
- 持仓刷失败（`fetcher.replace_one_holdings` 返回 `success=False`）：整个接口返回 `success=false`，**不调 prefilter 重算**，`prefilter_resynced=false`
- 持仓刷成功 + prefilter 重算成功：`success=true, prefilter_resynced=true, prefilter_error=null`
- 持仓刷成功 + prefilter 重算失败：`success=true, prefilter_resynced=false, prefilter_error="<例外文本或归类名>"`

### C-2 公共函数签名
```python
def _persist_prefilter_stock_list(
    stock_items,        # Iterable[StockBasicInfo] 或 Iterable[str] 都接
    date_str: str,
) -> None:
    """把 prefilter 后的股票代码单列写盘。

    调用方：
    1. refresh_dividend / main.py：传入 fetcher.get_stock_list 已算好的 list[StockBasicInfo]
    2. 单指数刷后本地重算：传入自己重算后的 list[str]

    内部：
    - 统一取 .code 或 str，zfill(6)
    - 构造 pd.DataFrame([{"股票代码": code} for ...)
    - save_csv_data(prefilter_df, "prefilter_stock_list", date_str)
    - logger.info 写盘成功

    Raises:
        ValueError: 当 stock_items 为空（与 commit 3c1dce4 行为一致：写盘前 assert）
    """
```

**为什么不是 `_compute_prefilter_stock_list(holdings_df, fhps_df)`**：
- `refresh_dividend` / `main.py` 已经从 `fetcher.get_stock_list()` 拿到算好的 `list[StockBasicInfo]`
- 那条路径不再做"算 prefilter"，所以抽"算 + 写"函数会接不进去
- "单指数刷后本地重算"是另一条独立路径（读汇总 CSV + fhps + 自己过滤），**不应与全量刷的 fetcher 路径强合并**
- 真实 DRY 价值是**写盘动作**这一步（`pd.DataFrame + save_csv_data + log`），所以只抽这一个

### C-3 写盘格式
- 文件名：`prefilter_stock_list_{YYYY-MM}.csv`
- 内容：单列股票代码，带列头 `股票代码`
- 必须用 `save_csv_data` 复用现有 helper（保证 `.gitignore` / 路径 / `日期目录` 行为一致）
- 列内类型：str，保留前导 0（用 `astype(str).str.zfill(6)` 与汇总裁减口径一致）

### C-4 前端类型 + 渲染契约
```ts
export interface IndexRefreshItem {
  code: string;
  name: string;
  success: boolean;
  constituents_count: number;
  error?: string | null;
  prefilter_resynced: boolean;        // NEW
  prefilter_error?: string | null;    // NEW
}

// page.tsx::getRowState 语义：
// success + prefilter_resynced 都为 true  → refreshed_success（显示 ✅）
// 其他任何情况（success=false 或 prefilter_resynced=false）→ refreshed_failed（显示 ✗ + 重试）
```

## Data Flow

### 单指数刷 + prefilter 重算 时序
```
POST /dividend/index-holdings/refresh { code: "000922" }
  │
  ├─▶ 锁 _is_refreshing
  ├─▶ fetcher.replace_one_holdings(code)
  │     ├─ ak.stock_xxx_cons_weight_csindex(symbol="000922")  [aks hare 调用]
  │     ├─ 读 红利指数持仓汇总_YYYY-MM.csv (load_csv_data)
  │     ├─ 删该指数旧行 + concat 新行
  │     ├─ 重算"纳入指数数量"+"交易所"
  │     └─ save_csv_data → 红利指数持仓汇总_YYYY-MM.csv
  │
  ├─ [NEW] if result.success:
  │     ├─ 读 红利指数持仓汇总_YYYY-MM.csv （上一步刚写）
  │     ├─ 读 fhps_20251231.csv
  │     ├─ _compute_prefilter_stock_list(holdings, fhps) → list[str]
  │     ├─ save_csv_data(prefilter_df, "prefilter_stock_list", date_str)
  │     └─ 失败 → logger.error, 不抛出
  │
  └─▶ return IndexRefreshItem(**result, prefilter_resynced=..., prefilter_error=...)
```

### status 接口比对逻辑（FR-1 改后）
```
GET /dividend/status
  ├─ 读 红利指数持仓汇总_YYYY-MM.csv → actual_index_codes
  ├─ 持仓覆盖度判断（holdings_complete）→ 给 holdings_status 字段（不动）
  ├─ 读 prefilter_stock_list_YYYY-MM.csv → target_count
  ├─ 读 近3年股息率汇总_YYYY-MM.csv → completed_count
  ├─ [改] needs_update = completed_count < target_count    ← 不再看 holdings_complete
  └─ return { needs_update, ..., holdings_status }        ← holdings_status 仍返回
```

### 前端渲染流
```
response.success && response.prefilter_resynced
  → getRowState 返回 refreshed_success
  → Page UI 显示 "✓ {constituents_count}只"
其他
  → getRowState 返回 refreshed_failed
  → Page UI 显示 "✗ {prefilter_error || error || '失败'}" + 重试按钮
```

## Tradeoffs（已决策项不再展开）

| 项 | 选择 | 备注 |
|---|---|---|
| FR-3 抽函数还是复制 | **抽**（用户拍板） | 扩改动到 main.py + 一致性测试 |
| prefilter 重算失败 | 静默 log + 显式标 | 不让 API 整体失败，但徽章不显示 ✅ |
| `holdings_complete` 用法 | 仅用于 response 字段 | 不再影响主按钮 needs_update |
| 单指数接口响应字段顺序 | 原有先行 + 新增后置 | 向后兼容 |

## 留待 PR 时确认的小决策

| 项 | 候选 | 默认 |
|---|---|---|
| 单指数接口响应字段命名 | `prefilter_resynced` vs `prefilter_resync` vs `prefilter_synced` | **resynced**（"重算"语义更准，akshare 不一定一致） |
| `_compute_prefilter_stock_list` 模块位置 | `routes.py` 私有 vs 抽出 `src/services/prefilter_service.py` | 私有（保持改动最小） |
| fhps_df 列名容错 | 严格 vs 模糊匹配 | 严格（让错误尽早冒头） |

## Compatibility

### 后端
- `IndexRefreshItem` 字段追加（最后两项），不删除旧字段 → 向后兼容
- `/dividend/status` response 字段不删，`needs_update` 含义变窄（覆盖度不参与），但**前端不依赖这个语义变化**（FR-1 是分母变小、不会让前端多等按钮）
- `holdings_status` 字段保留 → 前端 `IndexStatusPopover::getRowState` line 81 fallback 路径继续可用
- `prefilter_stock_list_YYYY-MM.csv` 格式不变

### 前端
- `IndexRefreshItem` 加字段（默认 `true`，兼容旧响应缺失字段） → 用 `?? true` 容错

```ts
const resynced = irItem.prefilter_resynced ?? true;  // 旧后端没字段时按"已成功"对待
```
> ⚠️ 这里有个细微决策：**旧后端没有 `prefilter_resynced` 字段时，前端按 "true" 还是 "false" 处理？**
> - `?? true`：旧接口响应下，徽章显示原状（success=true → ✅）
> - `?? false`：旧接口响应下，徽章退化（成功也不显示 ✅）
>
> 建议 `?? true`，保持"前端新字段兼容旧后端不破坏现状"。后端部署后再逐步收紧。

### CSV / Docker
- `prefilter_stock_list_YYYY-MM.csv` schema 不变
- Docker 部署按 CLAUDE.md 子模块流程：submodule update → build --no-cache → recreate

## Rollout

### 顺序（多仓原子保证）
1. `cd backend/dividend-select`
2. FR-3 抽函数 → 测试 → commit "refactor(prefilter): 抽 _compute_prefilter_stock_list 公共函数"
3. FR-3 改 refresh_dividend + main.py 调用新函数 → 测试 → commit
4. FR-1 删 `or not holdings_complete` → 测试 → commit "fix(dividend/status): 移除非主按钮的持仓覆盖度判断"
5. FR-2 + FR-4 单指数刷加 prefilter + 扩响应 → 测试 → commit "feat(dividend/index-holdings): 单指数刷成功后本地重算 prefilter"
6. push `backend/dividend-select` 到 origin main
7. 回主仓库 `git add backend/dividend-select` → commit "chore: bump dividend-select prefilter 重算+状态机重构"
8. push 主仓库
9. **前端**：本地 `pnpm tsc --noEmit` + 手动浏览器验证 → commit "refactor(dividend): IndexStatusPopover success 条件加严"
10. NAS/本地按 CLAUDE.md 子模块部署四件套：`git submodule update --init --recursive` + `docker compose build --no-cache` + `docker compose up -d --force-recreate`

### Rollback Points
- **单步可回退**：每个 commit 都按 PRD 边界小步走，单独 revert 不影响其他
- **回退顺序**（如果出问题）：先回退前端（前端的 `?? true` 容错已经兜底，但若 `page.tsx::getRowState` 渲染异常直接 revert 该 commit）→ 后端按 commit 顺序倒序回退

### 监控 / 验证
- 单指数刷 `prefilter_resynced=false` 比率：`SELECT count(*) WHERE prefilter_resynced=false` 应该 ≈ 0
- 主按钮 needs_update 分布：跑批 7 天，每日应保持稳定

