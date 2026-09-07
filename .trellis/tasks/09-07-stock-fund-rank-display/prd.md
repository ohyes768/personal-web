# 股票基金页面新增同类排名（基于 AkShare 雪球业绩接口）

## Goal

让股票基金筛选页（/funds/stock）在主表直接展示**第三方平台同类排名**，便于一眼识别"近期大热 vs 长期稳定"的基金，辅助"大热必死"的投资判断。数据源沿用现有 `ak.fund_individual_achievement_xq`，不引入新数据源；本次仅改股票 tab。

## Background（已确认事实）

- `FundAchievementRank` 表已存在（`backend/fund-select/src/db/models.py:97-114`），复合主键 `(code, period_kind, period)`，字段 `ret / max_dd / peer_rank`。
- `peer_rank` 形如 `"1014/5616"`，来自雪球蛋卷 `danjuanfunds.com/djapi/fundx/base/fund/achievement/{code}`。
- 实测 `ak.fund_individual_achievement_xq` 返回 32 行：`年度业绩`（成立以来 / 今年以来 / 2002-至今逐年）+ `阶段业绩`（近1月/3月/6月/1年/3年/5年/成立以来），均有 `peer_rank`。
- 入库流程 `backend/fund-select/src/services/refresh_service.py:97-106` **仅在 fund_type.startswith("股票型") / QDII 时入库**；债基不抓排名 → 债基 tab 不展示排名（见 AC-9）。
- 详情接口 `/api/funds/stock/{code}` 已挂 `achievement_ranks`（routes.py:221-242）。
- 列表接口 `/api/funds/stock/screen` 当前 DTO（`filter_service._to_dto()` filter_service.py:206-237）**未含排名**。
- 前端 `FundTable.tsx:127-225` 列顺序固定、已有表头悬停说明 `RISK_TIPS` 与脚注（line 220-224）风格可直接复用。
- 后端最近一次完整测试 162 passed（journal-1.md:176），`test_stock_filter_service.py` 已有覆盖。
- 前端无单测框架（journal-1.md:186-187），依赖最小化 + tsc / build 验证。

## User Value

- 主表一眼看到 4 个周期排名百分位 + 颜色梯度，与已有"近N年收益"列横向对照，秒判 **"热度 vs 持续度"**（例：近1年前5% 但近3年仅前47% → 大热警示）。
- 不必每次点开详情看排名；不需要重抓数据（沿用现有 ETL 库存）。

## Requirements

### REQ-1 后端 DTO：screen items 新增 4 个周期排名摘要

新增字段（命名如下，与前端 TS 接口对齐）：

| 字段 | 类型 | 来源 |
|---|---|---|
| `rank_ytd` | `{pct: number, total: number} \| null` | `FundAchievementRank` (年度业绩, 今年以来) |
| `rank_1y` | `{pct, total} \| null` | (阶段业绩, 近1年) |
| `rank_3y` | `{pct, total} \| null` | (阶段业绩, 近3年) |
| `rank_5y` | `{pct, total} \| null` | (阶段业绩, 近5年) |

- `pct = round((rank / total) * 100, 1)`，范围 0-100，越小越靠前。
- 解析：`"1014/5616"` → `{pct: 18.1, total: 5616}`；非 "数字/数字" → `null`；缺失或 peer_rank 为空 → `null`。
- 仅 stock tab 接口返回（债基无数据源约束）。

### REQ-2 后端：`FilterService._screen()` join `FundAchievementRank`

- 在 `_screen()`（filter_service.py:126-203）新增 `outerjoin`：
  - 4 次 subquery 分别取 4 个周期值，使用 `and_(FundAchievementRank.period_kind==?, period==?)`。
  - 在 `_to_dto()` 里组合。
- `_screen()` 同时被 `screen()` 和 `screen_stock()` 调用 → 债基接口会**多返回 null 字段**。**应对**：`_to_dto()` 不区分 kind，但前端类型层在债基忽略 4 个新字段（见 REQ-3）。

### REQ-3 前端：FundTable 新增 4 列，仅 stock tab 展示

- 新增 prop `showRankColumns?: boolean`，默认 `false`，stock page 传 `true`（与 `showRiskColumns` 模式一致）。
- 列顺序（股票 tab 完整列）：`代码 / 名称 / 类型 / 规模 / 年限 / 回撤 / 经理 / 近1年 / 近3年 / 近5年 / 排名·今年来 / 排名·近1年 / 排名·近3年 / 排名·近5年 / 6 风险列 / 年费 / 对比`。
- 列宽方案：**压缩现有列宽**（用户决策）
  - 现有列：代码 ~3.5rem / 名称 7rem / 类型 ~3rem / 规模 4rem / 年限 3rem / 经理 4rem
  - 压缩到：代码 3rem / 名称 5.5rem / 类型 2.5rem / 规模 3.5rem / 年限 2.5rem / 经理 3.5rem（腾出 ~5rem）
  - 新增 4 列各 3.5rem，可容纳。
  - 1280px 主流屏幕仍可读，无需横向滚动（实测验）。
- 表头使用 `SortableHeader` 但**不接 `onSort`**（v1 暂不支持"按排名排序"）。

### REQ-4 前端：排名百分位 chip + 颜色梯度

- 文本格式：`前 {pct}%`（如 `前 18.1%`）；缺失显示 `-`。
- 颜色梯度（Tailwind，沿用现有 `text-up / text-down / text-ink-soft`，新增 chip 背景）：

| pct | chip 样式 | 语义 |
|---|---|---|
| `≤ 10` | `bg-rank-top text-white` | 优秀 |
| `10 < pct ≤ 25` | `bg-rank-top-soft text-rank-top-strong` | 良好 |
| `25 < pct ≤ 50` | `bg-rank-mid text-ink-muted` | 中性 |
| `50 < pct ≤ 75` | `bg-rank-bottom-soft text-rank-bottom-strong` | 偏弱 |
| `> 75` | `bg-rank-bottom text-white` | 落后 |
| `null` | `text-ink-soft` | 显示 `-` |

- tooltip 走现有 `hover-tip`：`data-tip="周期 · 1694/5606"`（原始排名/总数），沿用 `data-tip` 风格。
- 表头悬停：复用 `SortableHeader` 的 `tip` prop：文案"同类排名：当前排名 ÷ 同类基金总数。**百分位越小越靠前**。口径：雪球蛋卷基金，同类基金按区间收益排序，分母随时间变化。"

### REQ-5 前端：表格脚注加"热度 ≠ 持续度"提示

- 在 `showRankColumns` 块下方加一行：
  > `小贴士：近 1 年排名靠前 ≠ 长期表现稳定，建议结合 4 个周期判断热度与持续度。`
- 样式：`mt-2 text-[10px] leading-relaxed text-ink-soft`（与现有 `showRiskColumns` 脚注 line 220-224 完全一致）。
- 完整脚注（与风险指标脚注合并展示或并列）：
  > `风险指标为近 3 年日频口径：基准取各基金业绩基准，无风险利率取 1 年定存；历史不足 250 个交易日的基金显示「-」。排名口径：雪球蛋卷基金 · 同类基金按区间收益排序。`

### REQ-6 测试

- 后端（pytest）：
  - `tests/test_stock_filter_service.py` 新增 1 个用例：stock 列表 DTO 含 4 个新字段，缺数据时为 null。
  - 新增 `tests/test_filter_service.py` 用例：`_parse_peer_rank` valid / malformed / None / 空字符串。
  - 全量 `pytest tests/ -v` 必须通过。
- 前端：
  - 依赖最小化，不新增单测框架。
  - `pnpm tsc --noEmit` 通过；`pnpm build` 成功（standalone symlink EPERM 与本任务无关，沿用既有）。
  - 截图：股票 tab 4 列颜色梯度视觉验证。

## Acceptance Criteria

| ID | 标准 |
|---|---|
| AC-1 | `GET /api/funds/stock/screen` 响应 items 中每只含 `rank_ytd / rank_1y / rank_3y / rank_5y`，存在缺失时为 null（不报 500） |
| AC-2 | `peer_rank="1014/5616"` → `{pct: 18.1, total: 5616}`；分母缺失或字符串异常 → `null` |
| AC-3 | stock page FundTable 主表新增 4 列，紧贴 `近5年` 后，列宽方案采用"压缩现有列宽"，1280px 屏幕不出现横向滚动 |
| AC-4 | 百分位 chip 显示为 `前 18.1%`，颜色梯度按 REQ-4 规则生效 |
| AC-5 | 表头悬停说明含口径文字；表格下方脚注含"热度 ≠ 持续度"+ 雪球蛋卷口径说明 |
| AC-6 | 后端 `pytest tests/ -v` 全量通过（≥162 个用例） |
| AC-7 | 前端 `pnpm tsc --noEmit` 通过；`pnpm build` 成功 |
| AC-8 | stock 页面截图，4 列颜色梯度在浅色背景清晰可辨；缺失数据优雅显示 `-` |
| AC-9 | 债基 tab FundTable **不**显示新增 4 列（保持原貌） |
| AC-10 | DTO 向后兼容：旧字段全部保留，无重命名 |

## Non-Goals（明确不做）

- ❌ 不引入新数据源；不重抓历史。
- ❌ 不在债基 ETL 业绩排名（债基刷新流程扩展要单独任务评估 ~4500 只基金抓取成本）。
- ❌ 不做"自然月排名"（2026-08 这类需要历史净值自行计算）。
- ❌ 不支持自定义区间排名。
- ❌ v1 不做"按排名排序"按钮（`rank_1y` 等不接入 sort 白名单）。
- ❌ 不暴露原始 `peer_rank="1694/5606"` 字符串到列表 DTO（详情接口保留完整 `achievement_ranks`）。

## Technical Notes

- 解析 helper：`filter_service.py` 顶部新增 `_parse_peer_rank(value: str | None) -> dict | None`：
  ```python
  def _parse_peer_rank(value):
      if not value or "/" not in value:
          return None
      try:
          rank, total = (int(x.strip()) for x in value.split("/", 1))
          if rank <= 0 or total <= 0 or rank > total:
              return None
          return {"pct": round(rank / total * 100, 1), "total": total}
      except (ValueError, TypeError):
          return None
  ```
- 后端 `_to_dto()` 新增：
  ```python
  rank_ytd = _rank_for(ach_map, "年度业绩", "今年以来")
  rank_1y = _rank_for(ach_map, "阶段业绩", "近1年")
  ...
  ```
  `ach_map = {row.period: _parse_peer_rank(row.peer_rank) for row in ach_rows}`。
- 前端 TS 类型：
  ```ts
  export interface RankPercentile {
    pct: number | null;
    total: number | null;
  }
  // 在 FundListItem 增加
  rank_ytd: RankPercentile | null;
  rank_1y: RankPercentile | null;
  rank_3y: RankPercentile | null;
  rank_5y: RankPercentile | null;
  ```
- Tailwind 颜色：`bg-rank-top / bg-rank-top-soft / bg-rank-mid / bg-rank-bottom-soft / bg-rank-bottom` + 对应文字色。如 Tailwind config 未配，新增到现有 `tailwind.config` / CSS variables（沿用 `09-04-stock-fund-sharpe-filter` 任务的样式组织方式）。

## Risks / Rollback

- 风险 1：若现有 `fund_achievement_rank` 表为空（首次刷新未跑），4 列全显示 `-`。**应对**：启动后端前确认表非空；如空则先手动 `POST /api/funds/stock/refresh`。
- 风险 2：4 次 subquery join 影响响应时延。**应对**：30 只名单下预计 <50ms，监控首屏。
- 回滚：DTO 字段向后兼容 → 仅需删除前端 `showRankColumns` 4 列 + `_to_dto()` 中 4 个键即可，不破坏既有契约。

## Out of Scope (deferred to future tasks)

- 债基 ETL 业绩排名扩展（需独立任务，评估 ETL 性能）。
- 按排名排序按钮（`sort_rank_*` 白名单）。
- "热度 vs 持续度"自动 chip（需在 ETL 外多走一轮判断）。
- 自然月 / 自定义区间排名（需离线计算 + 缓存）。
