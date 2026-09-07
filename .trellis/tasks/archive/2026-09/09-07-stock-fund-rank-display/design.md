# Design：股票基金页面同类排名

## 1. 架构与边界

**作用范围**：仅 `/api/funds/stock/*` 一条接口路径上的 DTO + 前端 stock page 的 FundTable。

```
┌─────────────────────────────────────────────────────────────────┐
│ Frontend (apps/fund-select)                                     │
│  app/stock/page.tsx ─► stockApi.screen(filters) ─► FundTable    │
│                                                       + 4 新列  │
└─────────────────────────────────────────────────────────────────┘
                            │ HTTP
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backend (backend/fund-select)                                   │
│  routes.py:stock_screen ─► FilterService.screen_stock ──► _screen│
│                                                     └► _to_dto │
│                                                       + 4 新键 │
│                  └─► outerjoin FundAchievementRank (4 次 subq)  │
└─────────────────────────────────────────────────────────────────┘
                            │ ORM
                            ▼
                Fund / FundPerformance / FundFees
                FundHoldingsBond / FundRiskMetrics
                FundAchievementRank        ← 已有数据
```

**边界**：
- 数据层（`FundAchievementRank` 表）不动，已有数据继续被 stock detail 接口消费。
- `refresh_service.py` 不动：本次不重抓、不改入库策略。
- 债基 tab **完全不动**（接口、前端、ETL 全保持原样）。
- 前端公共组件：`FundTable.tsx` 加可选 `showRankColumns` prop；不动 `SortableHeader`、不动 `FundsHeader`、不动 `FilterSidebar`。

## 2. 数据流

### 2.1 后端查询

`_screen()` 当前结构（filter_service.py:142-150）：
```python
select(Fund, FundPerformance, FundFees, FundHoldingsBond, FundRiskMetrics)
.outerjoin(FundPerformance, Fund.code == FundPerformance.code)
.outerjoin(FundFees, Fund.code == FundFees.code)
.outerjoin(FundHoldingsBond, Fund.code == FundHoldingsBond.code)
.outerjoin(FundRiskMetrics, Fund.code == FundRiskMetrics.code)
.where(Fund.is_active == True)
.where(Fund.code.in_(codes))
```

**新增 4 次 subquery 关联**（在 `_screen()` 末尾 join 段）：
```python
TARGETS = [
    ("年度业绩", "今年以来"),  # rank_ytd
    ("阶段业绩", "近1年"),     # rank_1y
    ("阶段业绩", "近3年"),     # rank_3y
    ("阶段业绩", "近5年"),     # rank_5y
]

rank_joins = []
for kind, period in TARGETS:
    sub = (
        select(
            FundAchievementRank.code.label("code"),
            FundAchievementRank.peer_rank.label("peer_rank"),
        )
        .where(FundAchievementRank.period_kind == kind)
        .where(FundAchievementRank.period == period)
        .subquery()
    )
    rank_joins.append(sub)

# 在 outerjoin 段依次 .outerjoin(rank_joins[0], ...) ... .outerjoin(rank_joins[3], ...)
# select(Fund, ..., rank_joins[0].c.peer_rank.label("rank_ytd_raw"), ..., rank_joins[3].c.peer_rank.label("rank_5y_raw"))
```

**简化方案**（最终采用）：不用 4 次 outerjoin，改用 1 次 in-memory dict，避免 ORM 复杂度：

```python
def _screen(self, ...):
    # ... 现有查询拿 rows ...
    rows = self.db.execute(q).all()  # 不动

    # 一次性取出命中 codes 的目标周期排名
    items_codes = [f.code for f, *_ in rows]
    targets_pairs = [
        ("年度业绩", "今年以来"),
        ("阶段业绩", "近1年"),
        ("阶段业绩", "近3年"),
        ("阶段业绩", "近5年"),
    ]
    ach_rows = self.db.execute(
        select(FundAchievementRank.code, FundAchievementRank.period_kind,
               FundAchievementRank.period, FundAchievementRank.peer_rank)
        .where(FundAchievementRank.code.in_(items_codes))
        .where(tuple_(FundAchievementRank.period_kind, FundAchievementRank.period).in_(targets_pairs))
    ).all()
    ach_map: dict[str, dict[str, str]] = {}  # code -> {(kind, period): peer_rank}
    for r in ach_rows:
        ach_map.setdefault(r.code, {})[(r.period_kind, r.period)] = r.peer_rank

    items = [self._to_dto(f, p, fee, hold, risk, ach_map.get(f.code, {})) for f, p, fee, hold, risk in rows]
    # ... 排序逻辑保持不变 ...
```

**为什么 in-memory**：
1. 30 只名单下，ach_rows ≤ 120 行（30×4），拉一次数据库然后在 Python 里 dict 查找比 4 次 subquery outerjoin 更易读；
2. 与现有 `_to_dto()` 调用方式最小改动；
3. 测试容易（不需要构造 4 个 subquery 的 fixture）；
4. 性能可接受。

### 2.2 DTO 形状

`_to_dto()` 新增 4 个键：

```python
{
    ...现有字段,
    "rank_ytd": _parse_peer_rank(ach_map.get(("年度业绩", "今年以来"))),
    "rank_1y":  _parse_peer_rank(ach_map.get(("阶段业绩", "近1年"))),
    "rank_3y":  _parse_peer_rank(ach_map.get(("阶段业绩", "近3年"))),
    "rank_5y":  _parse_peer_rank(ach_map.get(("阶段业绩", "近5年"))),
}
```

债基 tab 接口会返回这 4 个键但都是 `null`（因为 `ach_map` 没有数据）→ 前端债基页面不消费（`showRankColumns={false}`），向后兼容。

### 2.3 前端

`FundTable.tsx` 改动：

```tsx
interface FundTableProps {
  // ... 现有 props ...
  showRankColumns?: boolean;  // 新增
}

const RANK_PERIOD_TIPS: Record<string, string> = {
  rank_ytd: '同类排名（今年以来）：雪球蛋卷基金 · 百分位越小越靠前',
  rank_1y:  '同类排名（近 1 年）：雪球蛋卷基金 · 百分位越小越靠前',
  rank_3y:  '同类排名（近 3 年）：雪球蛋卷基金 · 百分位越小越靠前',
  rank_5y:  '同类排名（近 5 年）：雪球蛋卷基金 · 百分位越小越靠前',
};

function RankChip({ rank }: { rank: RankPercentile | null }) {
  if (!rank || rank.pct === null) return <span className="text-ink-soft">-</span>;
  const { pct, total } = rank;
  const colorClass =
    pct <= 10 ? 'bg-rank-top text-white' :
    pct <= 25 ? 'bg-rank-top-soft text-rank-top-strong' :
    pct <= 50 ? 'bg-rank-mid text-ink-muted' :
    pct <= 75 ? 'bg-rank-bottom-soft text-rank-bottom-strong' :
                'bg-rank-bottom text-white';
  const original = `${total ? Math.round(pct * total / 100) : '?'}/${total ?? '?'}`;
  return (
    <span className={`tnum text-[10px] px-1 py-0.5 rounded hover-tip ${colorClass}`}
          data-tip={`周期 · ${original}`}>
      前 {pct}%
    </span>
  );
}
```

新增 4 列插入位置：`{showRiskColumns && ...}` **之前**，因为 `showRankColumns` 与现有收益列语义更接近（紧贴 `近5年` 后）。

### 2.4 Tailwind 颜色

新增到 `apps/fund-select/tailwind.config.ts`（或现有的 CSS variables 文件，按项目组织）：

```css
:root {
  --rank-top: #047857;             /* emerald-700 */
  --rank-top-soft: #d1fae5;        /* emerald-100 */
  --rank-top-strong: #065f46;      /* emerald-800 */
  --rank-mid: #fef3c7;             /* amber-50 */
  --rank-bottom-soft: #fed7aa;     /* orange-200 */
  --rank-bottom-strong: #9a3412;   /* orange-800 */
  --rank-bottom: #b91c1c;          /* red-700 */
}
```

样式 class 在 `globals.css` 或 tailwind config 注册到 `@apply`，与最近任务 `09-04-stock-fund-sharpe-filter` 保持同一组织方式。

## 3. Trade-offs

| 决策 | 优点 | 代价 |
|---|---|---|
| in-memory dict 而非 4 次 subquery | 可读、易测、改动小 | 多 1 次 DB round-trip（30 只名单 < 1ms） |
| 仅 stock tab，不改债基 | 范围聚焦、债基 ETL 不变 | 债基无排名展示（用户已确认接受） |
| 不做"按排名排序"按钮 v1 | 不引 sort 白名单风险 | 用户不能用百分位排序（次要） |
| v1 不接入前端测试 | 不引入 vitest 框架 | 前端验证仅靠 tsc + 截图 |
| 4 列展开而非下拉 | 横向对照直观，符合"大热必死"判断 | 列数变多，需压缩现有列宽 |

## 4. 兼容性 & 回滚

**兼容性**：
- 后端 DTO **加键不删键**，所有现有字段保留。债基 tab 多了 4 个 null 字段，JSON 大小增加 < 200B。
- 前端 TS `FundListItem` 加 4 个可选字段 → 类型层兼容。
- 前端 FundTable 通过 `showRankColumns` 默认 `false` 保持现有渲染路径不变。

**回滚步骤**（如有需要）：
1. 后端 `_to_dto()` 删除 4 个键赋值 + 删除 `ach_map` 构造逻辑。
2. 前端 `FundTable.tsx` 删除 `showRankColumns` prop + 4 列 JSX + `RankChip` 组件。
3. 前端 `app/stock/page.tsx` 删除 `showRankColumns={true}` 传参。
4. 不需要回滚数据库或 ETL。

## 5. 风险与监控

- **风险 1**：`fund_achievement_rank` 表为空 → 启动前必须 SELECT COUNT(*) 验证。
- **风险 2**：4 个 subquery / in-memory dict 的潜在 N+1 → 监控 `/api/funds/stock/screen` 首屏耗时；30 只名单下预期 < 50ms。
- **风险 3**：雪球分母口径变化 → 颜色梯度是百分位（相对位置），分母变大变小不影响显示；tip 文字已说明"分母随时间变化"。

## 6. 实现顺序

按依赖自下而上：

1. `_parse_peer_rank` helper + 单测
2. `_screen()` 取 `ach_rows` + `_to_dto()` 装配 4 个键
3. `test_stock_filter_service.py` 加 1 个 DTO 形状用例
4. 前端 `FundListItem` 加 4 个字段类型
5. `FundTable.tsx` 加 `showRankColumns` + `RankChip` + 4 列 + 脚注
6. `app/stock/page.tsx` 传 `showRankColumns={true}`
7. 全量 pytest + 前端 tsc + build
8. 截图验证
