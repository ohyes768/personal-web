# Design：股票基金行点击详情弹框

## 1. 架构与边界

**作用范围**：仅 `/funds/stock` 路径上的 FundTable 与新组件 RowDetailDrawer。

```
┌─────────────────────────────────────────────────────────────────┐
│ Frontend (apps/fund-select)                                     │
│  app/stock/page.tsx                                              │
│    ├─ FundTable (onRowClick → setDetailFund)                    │
│    └─ RowDetailDrawer (fund, onClose)                           │
│           └─ stockApi.getDetail(code) → FundDetail              │
│                └─ 渲染 4 周期排名 + 年度业绩 + 费率明细         │
└─────────────────────────────────────────────────────────────────┘
                            │ HTTP (复用现详情接口)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backend (backend/fund-select, 不动)                              │
│  /api/funds/stock/{code} → FilterService.get_detail              │
│                             + achievement_ranks（routes.py:221）│
└─────────────────────────────────────────────────────────────────┘
```

**边界**：
- 后端 0 改动：DTO 字段保留（含 rank_ytd/_1y/_3y/_5y + fees + achievement_ranks）；回归预期 171 passed。
- 债基 tab 完全不动：不引入 onRowClick、不引入 RowDetailDrawer。
- `globals.css` `--color-rank-*` token 保留：抽屉内复用。
- `RANK_PERIODS` 后端常量原样保留：前端镜像同名常量。

## 2. 数据流

### 2.1 行点击 → 抽屉状态

```ts
// stock/page.tsx
const [detailFund, setDetailFund] = useState<FundListItem | null>(null);

<FundTable
  items={items}
  onRowClick={setDetailFund}
  ...
/>
<RowDetailDrawer
  fund={detailFund}
  onClose={() => setDetailFund(null)}
/>
```

`detailFund` 持有列表行 FundListItem（含 code/name 等基础信息），抽屉内部按 code 拉详情补全 fees + achievement_ranks。

### 2.2 抽屉内详情加载

```ts
function RowDetailDrawer({ fund, onClose }: Props) {
  const [detail, setDetail] = useState<FundDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!fund) {
      setDetail(null);
      return;
    }
    setLoading(true);
    let cancelled = false;
    stockApi.getDetail(fund.code)
      .then(d => { if (!cancelled) setDetail(d); })
      .catch(() => { if (!cancelled) setDetail(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fund?.code]);

  if (!fund) return null;
  // 渲染 mask + drawer
}
```

骨架屏：loading=true 时 3 张表位各渲染 5-8 行 `<div className="h-4 bg-paper-deep rounded animate-pulse" />`。

### 2.3 抽屉内容布局

```
┌─ mask ─────────────────────────────────────────────────────┐
│  ┌─ RowDetailDrawer (right-0, top-0, bottom-0) ─────────┐  │
│  │ Header: [005827] 招商行业精选股票     [X]            │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │ 同类排名（雪球蛋卷基金）                              │  │
│  │ ────────── 4 周期排名 ──────────                       │  │
│  │ 周期       │ 收益      │ 百分位       │ 同类排名     │  │
│  │ 今年以来   │ +12.45%   │ [前 18.1%]  │ 1014/5616    │  │
│  │ 近 1 年    │ +8.20%    │ [前 25.4%]  │ 1425/5615    │  │
│  │ ...                                                    │  │
│  │                                                       │  │
│  │ ────────── 历年年度业绩 ──────────                    │  │
│  │ 2025  │ +25.30% │ [前 12.1%] │ 600/4956             │  │
│  │ 2024  │ -8.20%  │ [后 70.5%] │ 3196/4533             │  │
│  │ ...                                                    │  │
│  │ 成立以来 │ +120.5% │ [前 5%]   │ 91/5615              │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │ 费率明细                                              │  │
│  │ 申购费(小额档)       │ 0.15%                          │  │
│  │ 赎回 <7天            │ 1.50%                          │  │
│  │ 赎回 7天~1年         │ 0.10%                          │  │
│  │ 赎回 ≥1年            │ 0.00%                          │  │
│  │ 管理费               │ 1.50%/年                       │  │
│  │ 托管费               │ 0.25%/年                       │  │
│  │ 销售服务费           │ -                              │  │
│  │ 年费合计             │ 1.75%/年                       │  │
│  └───────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### 2.4 FundTable 行交互

```tsx
<tr
  key={fund.code}
  onClick={onRowClick ? () => onRowClick(fund) : undefined}
  className={`border-b border-rule transition-colors hover:bg-paper-tint cursor-pointer ${
    selected ? 'bg-info-tint' : ''
  }`}
>
  ...
  <td>
    <button
      onClick={(e) => { e.stopPropagation(); onToggleCompare(fund); }}
      ...
    >
      {selected ? '已选' : '对比'}
    </button>
  </td>
</tr>
```

**关键**：`e.stopPropagation()` 阻止对比按钮冒泡触发行 click。

### 2.5 FundTable 列调整

移除（位置：`<SortableHeader label="年费" ...>` 与 4 个 `showRankColumns` 块）：
- 4 排名列 th + 4 排名列 td
- "年费"列 th + "年费"列 td
- 表头悬停说明 `RANK_TIPS` 常量
- `<RankChip>` 组件（不再被引用）
- `rankColor()` 函数（不再被引用；但保留作抽屉复用 — 见 §5）

保留：
- `RiskColor()` 等其他工具函数
- `RankPercentile` 类型
- `rank_ytd/_1y/_3y/_5y` 字段（DTO 兼容）

## 3. Trade-offs

| 决策 | 优点 | 代价 |
|---|---|---|
| 沿用 CompareDrawer 风格（右侧抽屉） | 视觉一致、复用 mask/Escape/overflow 模式 | 与对比抽屉无法同时打开（业务上不会） |
| 列表移除 4 排名 + 1 年费列 | 列数回退到 13 列、关键列更突出 | 用户需点行才能看次要信息 |
| 抽屉内一次性展示 3 张表 | 信息全、便于对比同一只基金的多个口径 | 抽屉较长（最长 ~500px），需内部滚动 |
| 历年年度业绩完整展示 | 含"成立以来"总成绩，长期视角 | 部分基金 15-20 行，需内部滚动 |
| 骨架屏渲染 | 感知快、立刻有反馈 | 需要额外的 skeleton 样式（与现有 loading 一致） |
| 不预拉详情 | 实现简单、接口压力小 | 每次点行都有 100-300ms 等待 |
| 后端 DTO 不动 | 完全向后兼容（保留 rank_* 字段） | DTO 多了 4 个永远不消费的字段（债基 DTO 有冗余但不为性能问题） |

## 4. 兼容性 & 回滚

**兼容性**：
- 后端 DTO 0 改动。
- 债基 tab 完全不动。
- `fund-select` 其他组件（如 CompareDrawer、CompareTable）不动。
- 前端 `types.ts` 不动（FundListItem / FundDetail / RankPercentile / FundFees 全部已定义）。
- globals.css `--color-rank-*` token 保留（抽屉复用 + RankChip 函数保留备查）。

**回滚步骤**：
1. FundTable 恢复 showRankColumns 块（4 列 + 4 td）+ 年费列；新增 `showRankColumns?: boolean` prop 默认 false，stock page 传 true。
2. 删除 `RowDetailDrawer.tsx`。
3. stock/page.tsx 移除 `setDetailFund` state 与 `onRowClick` 传参。
4. FundTable 行 onClick + stopPropagation 同步移除。

## 5. 实现顺序

按依赖自下而上：

1. **新建 `RowDetailDrawer.tsx`**：与 CompareDrawer 同款 mask+drawer 结构；骨架屏 + 3 张表渲染。
2. **FundTable**：删除 showRankColumns 相关 + 年费列；新增 onRowClick prop + 行 onClick + 按钮 stopPropagation。
3. **stock/page.tsx**：引入 RowDetailDrawer + state + 传参。
4. **tsc + build + 截图验证**。

## 6. 风险与监控

- **风险 1**：行 click 与对比按钮冲突 → e.stopPropagation() 隔离。
- **风险 2**：详情请求失败 → catch 兜底 + 显示"加载失败 -"文案 + 关闭按钮。
- **风险 3**：mask 点击关闭 → 已在 CompareDrawer 实现，复制即可。
- **风险 4**：与 CompareDrawer 同屏打开 → 业务上不可能（点击行时 CompareDrawer 关闭按钮先于新抽屉），如发生则后开者覆盖（z-index 都是 50）。
- **风险 5**：列表列宽回退导致"对比"列变宽 → 不影响功能。
