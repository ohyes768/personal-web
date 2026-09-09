# 股票基金列表列重排 + 详情风险块

## 大白话

股基·雪球三分法 (`/funds/stock`) 和股基·市场 (`/funds/discovery-stock`) 两个 tab 共享 `FundTable.tsx`，当前列表 17 列里有 12 列是可排序数值列（业绩 3 + 风险 6 + 基本 3），信息密度过高，"业绩"和"风险拆解"两类指标挤在一张表里，用户看不清。

本任务做两件事：

1. **列表瘦身**：风险拆解 5 列（IR / α / γ / α-IR / 超额 3y）从列表移除，进详情抽屉的"风险拆解"块；业绩 3 列（近 1y/3y/5y）改为双行（上行收益带颜色可排序，下行"百分位 chip + 排名/总数"），让"业绩好坏 + 同类位置"一眼看出
2. **后端补 1 个字段**：`RankPercentile` 加 `rank: number | null`（同类排名分子），前端才能展示 "前 12.3% · 25/204" 这种完整排名

## 范围

### 在范围内

| 层 | 改动 |
|---|---|
| 后端 service | `services/filter_service.py:84` `_parse_peer_rank` 多返回一个 `rank` 字段 |
| 前端类型 | `lib/types.ts` `RankPercentile` 接口加 `rank: number \| null` |
| 前端列表 | `components/FundTable.tsx` 删 5 列风险指标 + 业绩 3 列改双行 |
| 前端详情 | `components/RowDetailDrawer.tsx` 新增"风险拆解"块 |

### 不在范围内

- 债基 tab (`/funds/bond`, `/funds/discovery-bond`) —— 雪球 rank 4 周期对债基无数据，本次一行不改
- 净值曲线 / KPI 顶部卡 / 主题视图 / 跨 tab 对比 / 预设筛选 —— 后续任务
- `MarketFundRank` 表 / rankhandler 流水线 / 全量刷新 —— 已在 `09-08-market-fund-rankhandler` 任务

## Requirements

### 后端

#### R1 `_parse_peer_rank` 返回 `rank`

`backend/fund-select/src/services/filter_service.py:69-84`

- 输入：`'25/204'` 字符串
- 输出 dict 多加 `rank: int` 键
- 解析失败/格式异常 → 仍返回 `None`（不抛）

```python
return {"pct": round(rank / total * 100, 1), "total": total, "rank": rank}
```

### 前端

#### R2 `RankPercentile` 类型扩展

`apps/fund-select/src/lib/types.ts:6-9`

```ts
export interface RankPercentile {
  pct: number | null;
  total: number | null;
  rank: number | null;  // ← 新增；null 表示无数据或解析失败
}
```

#### R3 列表列改造（`FundTable.tsx`）

**删除列**（移到详情）：
- IR / 选股 α / 择时 γ / α-IR / 超额 3y — 共 5 列
- 连带 `showRiskColumns` prop 仅控制"夏普是否在列表"（保留夏普在列表）

**保留列**：
- 夏普（决策权重高，单字段代表风险调整收益）

**业绩 3 列改双行**：

`近 1y / 3y / 5y` 每列改为：
- 上行：收益数字（带颜色，正绿负红，可点击排序）
- 下行：`RankChip` 百分位 + "排名/总数" 文本（紧凑一行，例 `前 12.3% · 25/204`）

```tsx
<td className={`${td} text-right`}>
  <div className={`tnum whitespace-nowrap ${retColor(fund.ret_1y)}`}>
    {fmtRet(fund.ret_1y)}
  </div>
  <div className="flex items-center justify-end gap-1 text-[10px] text-ink-soft">
    <RankChip rank={fund.rank_1y} />
    {fund.rank_1y?.pct != null && (
      <span>前 {fund.rank_1y.pct.toFixed(1)}%</span>
    )}
    {fund.rank_1y?.rank != null && fund.rank_1y?.total != null && (
      <span>· {fund.rank_1y.rank}/{fund.rank_1y.total}</span>
    )}
  </div>
</td>
```

#### R4 详情新增"风险拆解"块（`RowDetailDrawer.tsx`）

在"费率明细"之前新增第 4 块卡片，标题"风险拆解"，表格两列：
- 字段名 + hover tip（复用现有 `RISK_TIPS` 文案）
- 数值（夏普 / IR / α / γ / α-IR / 超额 3y）

```tsx
<RankTable title="风险拆解">
  <table className="w-full text-xs">
    <tbody>
      {RISK_FIELDS.map(f => {
        const v = detail[f.key];
        return (
          <tr key={f.key} className="border-b border-rule">
            <td className="py-1.5 text-ink-strong" title={RISK_TIPS[f.key]}>
              {f.label}
            </td>
            <td className={`py-1.5 text-right tnum ${retColor(v)}`}>
              {f.format(v)}
            </td>
          </tr>
        );
      })}
    </tbody>
  </table>
</RankTable>
```

`RISK_FIELDS` 数组定义 6 个字段的 label + key + format（夏普 / IR / 选股α / 择时γ / α-IR / 超额3y）。

## 数据契约

### API 响应变化（仅向后兼容）

`GET /api/funds/{stock,discovery-stock}/screen` 返回的 `FundListItem`：

```ts
// 旧
rank_1y: { pct: number | null, total: number | null } | null

// 新
rank_1y: { pct: number | null, total: number | null, rank: number | null } | null
```

新字段为 `null` 时（旧后端返回时）前端展示不带 "25/204" 部分，仅 "前 12.3%"。**前端容错**：rank 为 null 时不渲染分子段。

## Out of Scope

- 债基 tab 改动
- 净值曲线（需后端补 nav_series 接口，另开任务）
- 详情顶部 KPI 卡（数据已有，纯前端改动，另开任务）
- 主题视图切换 / 跨 tab 对比 / 预设筛选 / 列显隐齿轮
- `MarketFundRank` 业绩表 / 4 阶段流水线 / 全量刷新按钮

## Acceptance Criteria

### 后端

- [ ] **AC1** `_parse_peer_rank('25/204')` 返回 `{'pct': 12.3, 'total': 204, 'rank': 25}`
- [ ] **AC2** `_parse_peer_rank('invalid')` 返回 `None`（不抛异常）
- [ ] **AC3** 现有 `pytest backend/fund-select/tests/test_discovery_filter_service.py` 全部通过（无回归）

### 前端

- [ ] **AC4** `pnpm tsc --noEmit` 通过（`RankPercentile.rank` 类型扩展不破坏现有引用）
- [ ] **AC5** `/funds/stock` 列表列：业绩 3 列改为双行展示；风险指标只剩夏普 1 列；无 IR / α / γ / α-IR / 超额 3y 列
- [ ] **AC6** `/funds/discovery-stock` 列表同上
- [ ] **AC7** `/funds/stock` 列表点击"近 1y/3y/5y"列头能按收益排序（行为不变）
- [ ] **AC8** 列表业绩列下行展示 "前 X.X% · rank/total" 紧凑一行，rank 为 null 时仅显示百分位
- [ ] **AC9** `/funds/stock` 点击行 → 详情抽屉"风险拆解"块展示 6 行：夏普 / IR / 选股α / 择时γ / α-IR / 超额3y
- [ ] **AC10** 详情"风险拆解"字段 hover 沿用 `RISK_TIPS` 文案
- [ ] **AC11** 债基 tab (`/funds/bond`, `/funds/discovery-bond`) 列表 / 详情完全无变化

### 数据

- [ ] **AC12** `curl /api/funds/stock/screen` 返回的 `items[0].rank_1y.rank` 是数字（25），不是 null（生产数据）
- [ ] **AC13** `items[0].rank_1y.pct` 仍为 12.3（精度不变）

## Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| `_parse_peer_rank` 多返回字段破坏 JSON 序列化契约 | 仅追加 key，类型可空；前端用可选链访问 |
| 列表列宽变化导致表格横向溢出 | 3 列双行总高度增加，但宽度不变；`min-w-0 overflow-x-clip` 已存在 |
| 详情新增块超出抽屉可视高度 | 抽屉已有滚动；新增块高度约 200px，可接受 |
| 债基 tab 引用 `RISK_FIELDS` 报错 | RISK_FIELDS 只在 `RowDetailDrawer.tsx`（股票专用）定义，债基用 `RowDetailDrawerBond.tsx` 不引用 |
| `RankPercentile.rank` 旧后端不返回 | 前端 rank === null 时不渲染分子段，向后兼容 |

## Notes

- 不动 `useFilters.ts` / `useCompare.ts` / `compareDimensions.ts` —— 这次只动 FundTable 和 RowDetailDrawer
- 不动后端 SQL —— `_parse_peer_rank` 是已有函数，仅多返回一个字段
- 后端改 1 行；前端改 2 个组件 + 1 个类型文件；总计 ~80 行 diff
</content>
</invoke>