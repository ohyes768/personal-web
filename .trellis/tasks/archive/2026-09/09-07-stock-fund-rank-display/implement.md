# Implement：股票基金页面同类排名

## 实施清单（按依赖顺序）

### Phase A：后端 helper + 单测（不依赖 UI）

- [ ] **A1**. 在 `backend/fund-select/src/services/filter_service.py` 顶部新增 helper：
  ```python
  def _parse_peer_rank(value: str | None) -> dict | None:
      """'1694/5606' → {'pct': 30.2, 'total': 5606}；格式异常/缺分母 → None。"""
  ```
- [ ] **A2**. `backend/fund-select/tests/test_filter_service.py` 新增用例：
  - `test_parse_peer_rank_valid`：验证 `"1694/5606"` → pct=30.2, total=5606
  - `test_parse_peer_rank_invalid`：验证 `"abc"`, `"1"`, `""`, `"1/0"`, `"-1/5"`, `"5/3"`（rank>total）→ None
  - `test_parse_peer_rank_none_input`：None → None

### Phase B：后端 `_screen()` + `_to_dto()`

- [ ] **B1**. 在 `FilterService._screen()`（filter_service.py:126-203）末尾、调用 `_to_dto()` 之前：
  - 一次性查 `FundAchievementRank`：`code / period_kind / period / peer_rank`
  - 仅查 4 个目标 (kind, period) 组合：`[("年度业绩","今年以来"), ("阶段业绩","近1年"), ("阶段业绩","近3年"), ("阶段业绩","近5年")]`
  - 装配 `ach_map: dict[str, dict[tuple[str, str], str | None]]`
- [ ] **B2**. `_to_dto()` 新增签名参数 `ach_map_for_code: dict | None = None`，新增 4 个键 `rank_ytd / rank_1y / rank_3y / rank_5y`，用 `_parse_peer_rank()` 转化。
- [ ] **B3**. 在 `_screen()` 调用 `_to_dto(f, p, fee, hold, risk, ach_map.get(f.code))`。

### Phase C：后端测试

- [ ] **C1**. `backend/fund-select/tests/test_stock_filter_service.py` 新增 1 个用例：
  - 准备：插入 N 只 Fund + 对应 4 个周期的 `FundAchievementRank` 行（覆盖率：完整 4 行 / 缺 1 行 / 全无 三种）
  - 断言：`screen_stock()` 返回的 items 每行含 4 个新键；完整 → 有 pct；缺数据 → None
- [ ] **C2**. `backend/fund-select/tests/test_filter_service.py` 或 `test_universe_isolation.py` 加 1 个用例：债基 `screen()` 返回 items 同样含 4 个键但值都是 None（接口契约向后兼容）。

### Phase D：前端类型 + 组件

- [ ] **D1**. `apps/fund-select/src/lib/types.ts` 新增类型 + 扩展 `FundListItem`：
  ```ts
  export interface RankPercentile {
    pct: number | null;
    total: number | null;
  }
  // FundListItem 增加：
  rank_ytd: RankPercentile | null;
  rank_1y:  RankPercentile | null;
  rank_3y:  RankPercentile | null;
  rank_5y:  RankPercentile | null;
  ```
- [ ] **D2**. `apps/fund-select/src/components/FundTable.tsx`：
  - `FundTableProps` 加 `showRankColumns?: boolean`
  - 文件顶部新增 `RANK_PERIOD_TIPS`（4 项）
  - 新增组件 `RankChip({ rank })`，渲染百分位 chip + 颜色梯度 + tooltip
  - 在 `<SortableHeader label="近5年">` 之后、`{showRiskColumns && ...}` 之前插入 4 个 `<SortableHeader label="排名·..." tip={...}>` + 4 个 `<td><RankChip rank={...} /></td>`
  - 表格下方新增 `showRankColumns` 块下的脚注（两行：热度 ≠ 持续度 + 雪球口径）
- [ ] **D3**. `apps/fund-select/src/app/stock/page.tsx` 调 `<FundTable ... showRankColumns showRiskColumns />`

### Phase E：Tailwind 颜色

- [ ] **E1**. 在 `apps/fund-select` 的全局样式 / Tailwind 配置中新增 5 个色阶：
  - `--rank-top` / `--rank-top-soft` / `--rank-top-strong`
  - `--rank-mid`
  - `--rank-bottom-soft` / `--rank-bottom-strong`
  - `--rank-bottom`
  - 注册对应 `bg-rank-*` 和 `text-rank-*` 类（如使用 CSS variables 体系）
  - 如用 Tailwind 默认色板，参考 design.md §2.4 的 hex

### Phase F：验证

- [ ] **F1**. 后端：`cd backend/fund-select && python -m pytest tests/ -v`，期望 ≥162 passed
- [ ] **F2**. 后端：`python -m pytest tests/test_stock_filter_service.py -v`，期望新用例通过
- [ ] **F3**. 前端：`cd apps/fund-select && pnpm tsc --noEmit`，期望通过
- [ ] **F4**. 前端：`pnpm build`，期望通过（standalone symlink EPERM 与本任务无关，沿用既有 skip 方式）
- [ ] **F5**. 启动后端 + 前端 dev server，访问 `/funds/stock`，截图：
  - 表格 4 列排名可见
  - 颜色梯度在浅色背景清晰
  - 缺失数据行显示 `-` 不破布局
- [ ] **F6**. 访问 `/funds/bond`，确认 4 列**不出现**，布局无变化

## 关键文件清单

| 文件 | 改动类型 |
|---|---|
| `backend/fund-select/src/services/filter_service.py` | A1 / B1-B3 |
| `backend/fund-select/tests/test_filter_service.py` 或新建 | A2 / C2 |
| `backend/fund-select/tests/test_stock_filter_service.py` | C1 |
| `apps/fund-select/src/lib/types.ts` | D1 |
| `apps/fund-select/src/components/FundTable.tsx` | D2 |
| `apps/fund-select/src/app/stock/page.tsx` | D3 |
| `apps/fund-select/tailwind.config.ts` 或 `globals.css` | E1 |

## 回滚点

任一 Phase 失败可单独回滚：
- Phase A-B 回滚：删除 helper + _to_dto 改动（不影响现有契约）
- Phase C 回滚：删除新增测试
- Phase D-E 回滚：删除前端 4 列 + chip + RankChip 组件（FundTable 回退到当前 13 列布局）
- Phase F 回滚：仅验证步骤，无文件改动

## 风险点（先验）

1. **数据缺失风险**：先 `python -c "from src.db.session import SessionLocal; from src.db.models import FundAchievementRank; from sqlalchemy import select, func; print(SessionLocal().execute(select(func.count()).select_from(FundAchievementRank)).scalar())"` 验证表非空。
2. **列宽风险**：实测验 1280px 宽度不出现横向滚动；如果出现，优先把"类型"列宽从 2.5rem 收到 2rem。
3. **Tailwind 颜色未生效**：如 `bg-rank-top` 类未识别，回退到 inline `style={{ background: '#047857' }}`（保留语义的同时绕过构建）。
