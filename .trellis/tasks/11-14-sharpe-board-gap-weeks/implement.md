# 实施计划：夏普榜单数据缺口周口径修正

## 0. 上下文

- 任务目录：`.trellis/tasks/11-14-sharpe-board-gap-weeks/`
- 需求：`prd.md`；设计：`design.md`
- 规格：
  - `.trellis/spec/backend/fund-select/backend/contracts.md`（§13 夏普榜单、§18 52 周窗口、§19 v3）
  - `.trellis/spec/frontend/fund-sharpe-board.md`（§2 图表、§3 状态与文案、§7 v2 窗口、§8 v3）

## 1. 后端聚合层（`backend/fund-select/src/services/sharpe_board_service.py`）

- [x] 1.1 新增 `_week_stale_codes(week) -> set[str]`：解析 `diagnostics_json.stale_codes`，
      容错 NULL / 非 dict / 非 list → 空集。
- [x] 1.2 `aggregate_board` 内建 `week_meta: dict[(source, week_start)] -> (status, stale_codes)`。
- [x] 1.3 新增内部判定 `_is_gap(code, week) -> bool`（按 scope 语义：all = 所有来源都缺口）。
- [x] 1.4 逐基金统计：`gap_weeks` / `evaluable_weeks`；`consecutive_weeks` 改为
      「listed 记 1 / gap 跳过 / miss 中断」。
- [x] 1.5 `item_keys` 同步加 `evaluable_weeks` / `gap_weeks`（§3a 陷阱）。
- [x] 1.6 `diagnostics` 增加 `gap_weeks`（周级：没发榜 或 有基金样本未更新），
      与既有 `no_board_weeks` 并存。

## 2. 后端 DTO（`backend/fund-select/src/api/models.py`）

- [x] 2.1 `SharpeBoardItemDTO`：`evaluable_weeks: int = 0`、`gap_weeks: list[date] = []`。
- [x] 2.2 `SharpeBoardDiagnosticsDTO`：`gap_weeks: list[date] = []`。

## 3. 前端 DTO + 展示

- [x] 3.1 `apps/fund-select/src/lib/sharpe-board.ts`：`SharpeBoardItem` 加两字段，
      `SharpeBoardDiagnostics` 加 `gap_weeks`。
- [x] 3.2 `components/sharpe-board/SharpeBoardTable.tsx`：
      「近52周在榜」→ `n/分母`（hover 说明分母 + 缺口周）；
      「最近连续周数」→ hover 说明「跨过 N 个数据缺口周」。
- [x] 3.3 `lib/sharpe-chart.ts`：`buildSharpeChartOption` 新增 `gapWeeks` 入参；
      markLine 竖线标记 + tooltip 文案（保持零依赖纯函数）。
- [x] 3.4 `components/sharpe-board/SharpeChart.tsx`：透传 `gapWeeks`。
- [x] 3.5 `app/sharpe-board/page.tsx`：把 `diagnostics.gap_weeks` 传给图表。
- [x] 3.6 `components/sharpe-board/SharpeBoardProfileCard.tsx`：有缺口周时追加说明行。

## 4. 测试

- [x] 4.1 后端 `backend/fund-select/tests/test_sharpe_board_service.py`：
      gap 周不打断连续、miss 周打断、`evaluable_weeks` 分母、`gap_weeks` 列表。
- [x] 4.2 后端 `tests/test_sharpe_board_api.py`：DTO 新字段出现在响应里（§3a 回归）。
- [x] 4.3 前端 `apps/fund-select/src/lib/sharpe-chart.test.ts`：缺口周标记 + tooltip 文案。
- [x] 4.4 前端 `apps/fund-select/src/lib/sharpe-board.test.ts`：新增字段的类型/格式化函数。

## 5. 校验命令

```bash
# 后端
cd backend/fund-select && uv run python -m pytest tests/ -q

# 前端（cwd apps/fund-select）
node --experimental-strip-types --test src/lib/sharpe-board.test.ts src/lib/sharpe-chart.test.ts
npx tsc --noEmit
pnpm build
```

- [x] 5.1 全部通过；生产库复核（容器内跑 `aggregate_board` 对 003598 / 008261 断言数值）。
- [x] 5.2 浏览器复核（部署后）：表格 `51/51`、连续 51、缺口周 hover、图表标记。

## 6. 文档（Phase 3.3 spec 更新）

- [x] 6.1 `contracts.md` 新增 §21：数据缺口周口径（判定模型、三个字段、DTO 三处同步、陷阱）。
- [x] 6.2 `fund-sharpe-board.md` 新增 §9：前端列语义变化 + 图表标记 + 测试要求。
- [x] 6.3 更新 `contracts.md` §3 与 §18 中「consecutive_weeks=缺席/未知中断」的旧表述
      （标注为 v2 旧口径，现行为「数据缺口不中断、真实缺席中断」）。

## 7. 提交（Phase 3.4）

- [ ] 7.1 后端 + 前端 + spec 一个功能提交；任务目录归档与 journal 走 `/trellis:finish-work`。
