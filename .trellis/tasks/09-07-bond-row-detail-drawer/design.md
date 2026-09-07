# Design：债基 tab 行点击详情抽屉

## 1. 架构与边界

**作用范围**：仅 `/funds`（债基）路径上的 FundTable 与新组件 RowDetailDrawerBond。

```
┌─────────────────────────────────────────────────────────────────┐
│ Frontend (apps/fund-select)                                     │
│  app/bond/page.tsx                                               │
│    ├─ FundTable (onRowClick → setDetailFund)                    │
│    └─ RowDetailDrawerBond (fund, onClose)                       │
│           └─ fundApi.getDetail(code) → FundDetail              │
│                └─ 渲染 持仓分析（饼图+集中度+前五大） + 费率明细 │
└─────────────────────────────────────────────────────────────────┘
                            │ HTTP (复用现详情接口)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backend (backend/fund-select, 不动)                              │
│  /api/funds/{code} → FilterService.get_detail + holdings        │
│  （routes.py:120-127 + holdings 已在 get_detail 返回）          │
└─────────────────────────────────────────────────────────────────┘
```

**边界**：
- 后端 0 改动。
- 股票 tab 完全不动：RowDetailDrawer 不引入 RowDetailDrawerBond 相关；stock/page.tsx 不动。
- 新建独立组件（不复用 RowDetailDrawer 内部组件）：用户决策。
- FEE_ROWS 抽到 `lib/feeRows.ts` 复用：避免代码重复 + 维护成本。

## 2. 数据流

### 2.1 行点击 → 抽屉状态

```ts
// bond/page.tsx
const [detailFund, setDetailFund] = useState<FundListItem | null>(null);

<FundTable ... onRowClick={setDetailFund} />
<RowDetailDrawerBond
  fund={detailFund}
  onClose={() => setDetailFund(null)}
/>
```

### 2.2 抽屉内详情加载

```ts
function RowDetailDrawerBond({ fund, onClose }: Props) {
  const [detail, setDetail] = useState<FundDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!fund) {
      setDetail(null);
      return;
    }
    setLoading(true);
    let cancelled = false;
    fundApi.getDetail(fund.code)              // ← 债基路由，不是 stockApi
      .then(d => { if (!cancelled) setDetail(d); })
      .catch(() => { if (!cancelled) setDetail(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fund?.code]);
}
```

### 2.3 持仓分析布局

```
┌─ RowDetailDrawerBond ─────────────────────────────────────┐
│ Header: [217022] 招商产业债券 · 债券型-普通债券  [X]      │
├──────────────────────────────────────────────────────────┤
│ 持仓分析（2025-12-31 报告期）                             │
│ ──────────────────────────────────────────────────────   │
│                                                           │
│  ┌─────────┐    利率债    2.6%   ▆▆                       │
│  │  ◐◑◒◓  │    信用债   14.1%   ▆▆▆▆▆▆▆▆▆               │
│  │ (圆环)  │    可转债    0.0%   ▆                       │
│  └─────────┘    其他     83.3%   ▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆ │
│                                                           │
│ ──────────────────────────────────────────────────────   │
│ 持仓集中度                                                │
│ 前 5 大债券占比：16.7%                                    │
│ [██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 33% (16.7/50)   │
│                                                           │
│ ──────────────────────────────────────────────────────   │
│ 前五大债券明细                                            │
│ 21民生银行永续债01      6.8%                              │
│ 25进出01                2.6%                              │
│ 25国开01                2.6%                              │
│ 21中国信达债01          2.5%                              │
│ 23太保寿险永续债01      2.2%                              │
├──────────────────────────────────────────────────────────┤
│ 费率明细                                                  │
│ 申购费(小额档)       0.80%                                │
│ 赎回 <7天            1.50%                                │
│ 赎回 7天~1年         0.10%                                │
│ 赎回 ≥1年            0.00%                                │
│ 赎回 ≥7天            -                                    │
│ 管理费               0.70%/年                             │
│ 托管费               0.20%/年                             │
│ 销售服务费           -/年                                 │
│ 年费合计             0.90%/年                             │
└───────────────────────────────────────────────────────────┘
```

### 2.4 圆环图 SVG 实现

```tsx
const HOLDING_COLORS = {
  rate:        'var(--color-info)',
  credit:      'var(--color-accent)',
  convertible: 'var(--color-up)',
  other:       'var(--color-rule-strong)',
} as const;

function DonutChart({ rate, credit, convertible }: ...) {
  const segments = [
    { label: '利率债',    pct: rate ?? 0,        color: HOLDING_COLORS.rate },
    { label: '信用债',    pct: credit ?? 0,      color: HOLDING_COLORS.credit },
    { label: '可转债',    pct: convertible ?? 0, color: HOLDING_COLORS.convertible },
  ];
  const sumKnown = segments.reduce((s, x) => s + x.pct, 0);
  const other = Math.max(0, 100 - sumKnown);
  if (other > 0.5) segments.push({ label: '其他', pct: other, color: HOLDING_COLORS.other });

  // 圆周长（外径 60 + 内径 40 的中线，半径 50）
  const C = 2 * Math.PI * 50;
  let offset = 0;
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 120 120" className="w-32 h-32 shrink-0">
        {segments.map((s, i) => {
          const len = (s.pct / 100) * C;
          const dasharray = `${len} ${C - len}`;
          const dashoffset = -offset;
          offset += len;
          return (
            <circle
              key={i}
              cx="60" cy="60" r="50"
              fill="none"
              stroke={s.color}
              strokeWidth="20"
              strokeDasharray={dasharray}
              strokeDashoffset={dashoffset}
              transform="rotate(-90 60 60)"
            />
          );
        })}
        <text x="60" y="60" textAnchor="middle" dy="0.35em" className="text-xs fill-ink-muted">100%</text>
      </svg>
      <ul className="text-xs space-y-1">
        {segments.map(s => (
          <li key={s.label} className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: s.color }} />
            <span className="text-ink-strong">{s.label}</span>
            <span className="text-ink-muted">{s.pct.toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

**关键**：用 `stroke-dasharray` + `stroke-dashoffset` 实现圆环拼接；`transform="rotate(-90)"` 让第一段从 12 点钟方向开始。

### 2.5 top5_bonds 解析

```ts
function parseTop5Bonds(s: string | null | undefined): Array<{ name: string; pct: number }> {
  if (!s) return [];
  return s.split('; ')
    .map(line => {
      const m = line.match(/^(.+?)\(([\d.]+)%\)$/);
      if (!m) return null;
      return { name: m[1], pct: Number(m[2]) };
    })
    .filter((x): x is { name: string; pct: number } => x !== null);
}
```

实际数据 `21民生银行永续债01(6.8%); 25进出01(2.6%); ...` → 解析为 5 行表格。

### 2.6 集中度进度条

```tsx
const concentration = detail?.holdings?.top5_concentration ?? null;
const max = 50;  // 量程
const pct = concentration === null ? 0 : Math.min(concentration, max);
const ratio = (pct / max) * 100;
const color =
  concentration === null ? 'bg-paper-deep'
  : concentration <= 30 ? 'bg-up'
  : concentration <= 50 ? 'bg-star'
  : 'bg-down';

<div className="flex items-center gap-2">
  <div className="text-sm text-ink-strong">前 5 大债券占比</div>
  <div className="text-sm tnum text-ink-strong font-medium">
    {concentration === null ? '-' : `${concentration.toFixed(1)}%`}
  </div>
</div>
<div className="h-2 bg-paper-deep rounded-full overflow-hidden">
  <div className={`h-full ${color} transition-all`} style={{ width: `${ratio}%` }} />
</div>
```

### 2.7 FEE_ROWS 抽到 `lib/feeRows.ts`

```ts
// apps/fund-select/src/lib/feeRows.ts
import type { FundDetail } from './types';

export const FEE_ROWS: Array<{ key: keyof NonNullable<FundDetail['fees']>; label: string; suffix?: string }> = [
  { key: 'fee_buy_small',   label: '申购费(小额档)' },
  { key: 'fee_redeem_lt7d',  label: '赎回 <7天' },
  { key: 'fee_redeem_7d_1y', label: '赎回 7天~1年' },
  { key: 'fee_redeem_ge1y',  label: '赎回 ≥1年' },
  { key: 'fee_redeem_ge7d',  label: '赎回 ≥7天' },
  { key: 'fee_mgmt',         label: '管理费',     suffix: '/年' },
  { key: 'fee_custody',      label: '托管费',     suffix: '/年' },
  { key: 'fee_service',      label: '销售服务费', suffix: '/年' },
];
```

然后 RowDetailDrawer 和 RowDetailDrawerBond 都 import。

## 3. Trade-offs

| 决策 | 优点 | 代价 |
|---|---|---|
| 新建独立 RowDetailDrawerBond | 组件职责单一；持仓/饼图逻辑不污染股票抽屉 | mask + Escape + 响应式宽度 ~30 行重复 |
| FEE_ROWS 抽到 lib/feeRows.ts | 消除 8 行重复；维护一致 | 多一个文件 |
| 手写 SVG 饼图 | 无图表依赖；可控样式；4 段拼接精度高 | 算法稍复杂（需测试） |
| 其他档（rate+credit+convertible 之差） | 反映"现金/同业存单/ABS"等真实持仓 | 用户可能不熟悉"其他"语义 → 加 tooltip 说明 |
| 集中度进度条 0-50% 量程 | 50% 已算高度集中；超过显示红 | 极个别奇葩基金可能 > 100%（永续债杠杆），需截断显示 |
| 不展示业绩 / 经理 / 基础信息 | 精简；避免列表重复 | 部分用户可能想看历史回撤（1y/5y） |

## 4. 兼容性 & 回滚

**兼容性**：
- 后端 0 改动。
- 股票 tab 完全不动。
- FundTableProps 不引入新 prop（沿用 stock 任务已有的 onRowClick）。
- 列表"年费"列移除：DTO 仍含 `fee_annual` 字段（向后兼容，债基 page 不传不影响）。

**回滚步骤**：
1. 删除 `RowDetailDrawerBond.tsx` 和 `lib/feeRows.ts`（可选）。
2. bond/page.tsx 移除 setDetailFund state + RowDetailDrawerBond 渲染。
3. FundTable 恢复"年费"列 th 和 td。

## 5. 实现顺序

1. **`lib/feeRows.ts`**：抽 FEE_ROWS。
2. **`RowDetailDrawer.tsx` 重构**：FEE_ROWS 从 lib/feeRows.ts import。
3. **`RowDetailDrawerBond.tsx`** 新建：持仓表（含 DonutChart + ConcentrationBar + Top5Table）+ 费率表。
4. **`FundTable.tsx`**：删除"年费"列 th 和 td。
5. **`bond/page.tsx`**：引入 RowDetailDrawerBond + state + 传参。
6. **验证**：tsc + 截图 + pytest 171。

## 6. 风险与监控

- **风险 1**：饼图 SVG 拼接出错（错位 / 比例失真）→ 简单单测覆盖（拼接总和 = 100%）。
- **风险 2**：top5_bonds 字符串格式异常 → try/catch + 显示原始字符串。
- **风险 3**：饼图配色与项目色板冲突 → 沿用 globals.css 已有语义色（info/accent/up/rule-strong），已验证对比度足够。
- **风险 4**：FEE_ROWS 抽取后 RowDetailDrawer 引用错误 → 同步更新 import 即可。
