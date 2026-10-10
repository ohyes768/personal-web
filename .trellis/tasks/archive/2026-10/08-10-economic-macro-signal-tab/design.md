# Design — economic 宏观信号 Tab

> 修订 v3(2026-08-10): 按 demo v2 终稿。删除 score / 维度级 data_date / 评分色阶 / ScoreBadge;保留 skill 定性结论作为卡头主信号(20px 加粗白);指标级 updated_at。组件命名 `GroupCard`(替代 DimensionCard)。

## 1. 模块文件布局

```
apps/economic/src/
├── app/modules/economic/
│   ├── page.tsx                              # 修改: 加第 8 个 Tab + dynamic import
│   └── components/
│       ├── MacroSignalTab.tsx                # 新增: 容器组件(含 loading 态管理)
│       └── macro-signal/
│           ├── MonthSwitcher.tsx             # 新增: 月份切换器
│           ├── GroupCard.tsx                 # 新增: 单张分组卡片(卡头双行 + 指标列表)
│           ├── GroupCardGrid.tsx             # 新增: 6 张卡片网格
│           ├── ReleaseCalendar.tsx           # 新增: 发布日历视图
│           └── constants.ts                  # 新增: GROUP_META + INDICATOR_LABELS(无 SCORE_COLOR_MAP)
├── lib/
│   ├── types/
│   │   └── economic.ts                       # 修改: TabType 加 'macro-signal'
│   └── modules/
│       └── macro-signal/
│           ├── types.ts                      # 新增: MacroIndicator / MacroSignalGroup / MacroSignalSnapshot / MacroSignalTabProps
│           ├── mock-data.ts                  # 新增: 3 个月 mock 数据 + loadMockSnapshot 异步函数
│           └── release-rules.ts              # 新增: 各分组发布日期生成函数
```

## 2. Props 契约(对外接口)

### 2.1 核心类型(`lib/modules/macro-signal/types.ts`)

```typescript
/** 分组 key(对齐 skill 的 dimension 字段) */
export type DimensionKey =
  | 'monetary_policy'
  | 'money_supply'
  | 'entity_economy'
  | 'inflation'
  | 'exchange_rate'
  | 'risk_appetite';

/** 单个指标(每个指标自带更新时间,粒度到指标级) */
export interface MacroIndicator {
  key: string;                       // 'cpi_yoy' / 'dr007' / ...
  value: number | null;              // null = 本月无数据
  updated_at: string | null;         // 'YYYY-MM-DD',null = 本月无数据
}

/** 一个分组(6 大主题之一)= skill 定性结论 + 该分组下指标列表 */
export interface MacroSignalGroup {
  conclusion: string | null;         // skill 的定性结论,如「温和」「适度宽松」;null = 整组缺失
  indicators: MacroIndicator[];      // 空数组 = 整组缺失
}

/** 一个月快照 = 6 个分组 */
export interface MacroSignalSnapshot {
  month: string;                     // 'YYYY-MM'
  groups: Record<DimensionKey, MacroSignalGroup>;
  generated_at?: string;             // ISO timestamp
}

/** 容器组件 Props —— 切换月份 = 调 loadSnapshot */
export interface MacroSignalTabProps {
  loadSnapshot: (month: string) => Promise<MacroSignalSnapshot | null>;
  availableMonths: string[];
  initialMonth?: string;
}
```

### 2.2 关键设计决策

- **删除 score / 维度级 data_date** —— 用户明确说不要评分;每个指标的更新时间用指标级 updated_at 表达,分组级 data_date 冗余。
- **保留 conclusion 作为卡头主信号** —— 20px 加粗白色,成为卡片视觉重心。
- **6 大主题只作分组容器** —— 不展示评分、不染色,纯粹按主题归类指标。
- **Props 用 `loadSnapshot` 异步函数** —— 切换月份触发请求,与真实接口语义一致。mock 阶段父级传 `loadMockSnapshot`,后续 agent 替换为 `fetch('/api/macro/signal?month=...').then(r => r.json())`,组件代码零改动。
- **loading 态显式可见** —— 切换月份后 6 张卡片整体显示 loading 占位(不是上一月数据保留)。
- **开放式 indicator key** —— 用 `string` 而非 union,允许 skill 未来扩展新指标(如 PMI 分项);前端查 INDICATOR_LABELS 表翻译,fallback 到原 key。
- **不与 EconomicDataResponse 耦合** —— Props 类型独立放在 `lib/modules/macro-signal/types.ts`。

## 3. 组件职责

### 3.1 `MacroSignalTab`(容器)

- 接收 `loadSnapshot + availableMonths + initialMonth?`
- 内部状态: `selectedMonth`、`snapshot: MacroSignalSnapshot | null`、`loading: boolean`、`error: string | null`
- `useEffect([selectedMonth])` → set loading true → try `await loadSnapshot(selectedMonth)` → set snapshot 或 null + set error → finally set loading false
- 渲染:
  - 顶部:`MonthSwitcher`
  - 中部:loading 时显示 loading 占位;error 显示错误占位;否则 `GroupCardGrid`
  - 底部:`ReleaseCalendar`(loading 时也显示当前选中月,因为发布规则与数据无关)
- 不接 `fullData` / `refreshKey` / `onRefreshSuccess` —— 数据通道独立

### 3.2 `MonthSwitcher`

- 输入:`currentMonth`、`availableMonths`、`onChange`
- 渲染:`< 上一月 [月份下拉] 下一月 >`
- 月份下拉显示「YYYY 年 M 月」,基于 availableMonths 排序生成
- 禁用态:currentMonth 是最小/最大时分别禁用上一月/下一月按钮

### 3.3 `GroupCard`(单张分组卡)

- 输入:`{ groupKey: DimensionKey; group: MacroSignalGroup }`
- 卡头第一行(小字标识):圆点(查 GROUP_META[groupKey].calendarColor)+ 分组名(查 GROUP_META[groupKey].title)+ 右侧「N 项指标」
- 卡头第二行(主信号):conclusion(20px 加粗白色 text-xl font-bold text-white tracking-wide);group.conclusion === null 时显示「数据缺失」(text-gray-600)
- 指标列表(每行):
  - 左侧:label(查 INDICATOR_LABELS[key].label) + 下方小字「updated_at · N 天前」
  - 右侧:value(查 INDICATOR_LABELS[key] 取 digits/unit,格式化)
  - value === null 显示 `—`(text-gray-600);updated_at === null 显示「本月无数据」
  - updated_at 距 selectedMonth 月初 35 天以上:时间用 text-yellow-600 + 「· 数据偏旧」
- 整组 indicators 为空:列表区显示「本月数据缺失」灰字占位

### 3.4 `GroupCardGrid`

- 输入:`{ groups: Record<DimensionKey, MacroSignalGroup> }`
- 按 DIMENSION_META 顺序遍历 6 个 key,渲染 6 个 GroupCard
- grid 布局: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4`

### 3.5 `ReleaseCalendar`

- 输入:`{ month: string }`(只需月份,不需 groups 数据)
- 用 release-rules.ts 算每个分组在该月的发布日期 → 聚合为 `{ date: DimensionKey[] }` map
- 渲染 6×7 周一起始日历,空位补灰格;每个有发布的日期画 N 个色点(查 GROUP_META[key].calendarColor)
- 点击单元格弹出 popover(用 useState + absolute 定位,不引库)
- 今日蓝边框(bg-blue-900/20 border-blue-500),未来日期 opacity-50

## 4. constants.ts(常量表)

```typescript
import type { DimensionKey } from '@/lib/modules/macro-signal/types';

export const GROUP_META: Record<DimensionKey, {
  title: string;
  order: number;
  calendarColor: string;  // 日历色点用,固定颜色(仅区分维度身份,与评分无关)
}> = {
  monetary_policy: { title: '货币政策', order: 1, calendarColor: 'bg-blue-500'    },
  money_supply:    { title: '信用扩张', order: 2, calendarColor: 'bg-emerald-500' },
  entity_economy:  { title: '经济运行', order: 3, calendarColor: 'bg-purple-500'  },
  inflation:       { title: '通胀环境', order: 4, calendarColor: 'bg-orange-500'  },
  exchange_rate:   { title: '外部压力', order: 5, calendarColor: 'bg-cyan-500'    },
  risk_appetite:   { title: '市场情绪', order: 6, calendarColor: 'bg-pink-500'    },
};

/** indicator key → 中文 label + 单位 + 小数位(开放式,查不到 fallback 到原 key) */
export const INDICATOR_LABELS: Record<string, { label: string; unit?: string; digits?: number }> = {
  dr007:              { label: 'DR007',              unit: '%',  digits: 3 },
  lpr_1y:             { label: '1年期 LPR',          unit: '%',  digits: 2 },
  mlf_1y:             { label: '1年期 MLF',          unit: '%',  digits: 2 },
  m2_yoy:             { label: 'M2 同比',            unit: '%',  digits: 1 },
  m1_yoy:             { label: 'M1 同比',            unit: '%',  digits: 1 },
  social_yoy:         { label: '社融存量同比',        unit: '%', digits: 1 },
  pmi_manufacturing:  { label: '制造业 PMI',         unit: '%', digits: 1 },
  industrial_yoy:     { label: '工业增加值同比',     unit: '%', digits: 1 },
  fai_yoy:            { label: '固定资产投资同比',   unit: '%', digits: 1 },
  retail_yoy:         { label: '社零同比',           unit: '%', digits: 1 },
  electricity_yoy:    { label: '工业用电量同比',     unit: '%', digits: 1 },
  railway_yoy:        { label: '铁路货运量同比',     unit: '%', digits: 1 },
  cpi_yoy:            { label: 'CPI 同比',           unit: '%',  digits: 1 },
  ppi_yoy:            { label: 'PPI 同比',           unit: '%',  digits: 1 },
  core_cpi_yoy:       { label: '核心 CPI 同比',      unit: '%', digits: 1 },
  dollar_index:       { label: '美元指数',           digits: 2 },
  usd_cny:            { label: '美元兑人民币',       digits: 4 },
  ted_spread:         { label: 'TED 利差',           unit: '%', digits: 2 },
  total_amount_yi:    { label: '两市成交额',         unit: '亿', digits: 0 },
  turnover_rate:      { label: '换手率',             unit: '%',  digits: 2 },
  margin_balance_yi:  { label: '融资融券余额',       unit: '亿', digits: 0 },
};
```

## 5. release-rules.ts(发布日历规则)

```typescript
export function getWorkdayOnOrBefore(y: number, m: number, d: number): Date | null { ... }
export function getWorkdaysInMonth(y: number, m: number): Date[] { ... }

/** 对给定月份,返回每个分组在该月的发布日期数组(YYYY-MM-DD) */
export function getReleaseDates(month: string, groupKey: DimensionKey): string[] {
  // monetary_policy: DR007 每工作日 + MLF 15日 + LPR 20日(都工作日校正)
  // money_supply:    M2/M1/社融 12-15 日窗口,取第一个工作日
  // entity_economy:  铁路货运 7日 + 工业增加值/固投/社零 13日 + 用电量 20日(都工作日校正)
  // inflation:       CPI/PPI 10日(工作日校正)
  // exchange_rate:   每工作日
  // risk_appetite:   每工作日
}
```

## 6. mock-data.ts(3 个月快照 + 异步加载)

- 数据结构: `MOCK_DATA: Record<string, MacroSignalSnapshot>` 按 month 索引
- 2026-05 数据从 skill JSON 直接复制 conclusion,所有指标值 + 配上 updated_at
- 2026-04 / 2026-03:数值 ±10% 扰动,updated_at 前移一月,conclusion 调整(如通胀「温和」→「低通胀偏冷」)
- 2026-03 risk_appetite 设为 `{ conclusion: null, indicators: [] }` 演示空分组
- 导出 `MOCK_AVAILABLE_MONTHS = ['2026-03', '2026-04', '2026-05']`
- 导出 `loadMockSnapshot(month: string): Promise<MacroSignalSnapshot | null>`:
  ```typescript
  return new Promise(resolve => {
    setTimeout(() => resolve(MOCK_DATA[month] ?? null), 300);
  });
  ```

## 7. page.tsx 修改点(最小侵入)

```typescript
import { loadMockSnapshot, MOCK_AVAILABLE_MONTHS } from '@/lib/modules/macro-signal/mock-data';

const MacroSignalTab = dynamic(() => import('./components/MacroSignalTab').then(mod => ({ default: mod.MacroSignalTab })), {
  ssr: false,
  loading: () => <div className="h-[700px] flex items-center justify-center text-gray-400">加载宏观信号...</div>
});

// tabs 数组追加:
{ id: 'macro-signal', label: '宏观信号', description: '当月 6 维度宏观判断卡片 + 发布日历' }

// 在所有 Tab 容器 div 之后追加:
<div hidden={activeTab !== 'macro-signal'}>
  <MacroSignalTab
    loadSnapshot={loadMockSnapshot}
    availableMonths={MOCK_AVAILABLE_MONTHS}
  />
</div>

// handleTabChange 不需要特判 macro-signal(它不用 timeRange)
```

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 自研日历工作日计算易错 | 写单元函数 `getWorkdayOnOrBefore` 辅助,实现简单可读 |
| INDICATOR_LABELS 表不全 | 查询时 fallback 到 `{ label: key, digits: 2 }`,不抛错 |
| mock 数据手写 3 份费力 | 本月复制 skill JSON,另两月用 helper `shiftSnapshot(snapshot, monthOverride, factor)` 生成 |
| `loadSnapshot` 异步失败 | 组件 catch error 显示错误占位;mock 阶段不会失败但代码路径已就位 |
| 后端 agent 实现时把 score 也塞进返回 | 前端类型定义不含 score,JSON 多余字段被忽略 |

## 9. 不做的事(明确边界)

- ❌ 不展示 score 数字
- ❌ 不做评分色阶染色
- ❌ 不写后端、不动 global-macro-fin submodule、不改 BFF 代理路由
- ❌ 不引入 date-fns/dayjs/moment / UI 库
- ❌ 不与 `useFullEconomicData` 共享数据
- ❌ 不写测试(P0 阶段 lint + build 过即可)
