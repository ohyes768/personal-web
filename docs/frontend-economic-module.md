# 前端宏观经济数据模块说明

本文档描述前端宏观经济数据展示页面的模块结构和使用方法。

---

## 模块结构

```
frontend/src/app/modules/economic/
├── page.tsx                  # 主页面组件
├── components/
│   ├── EconomicChart.tsx     # 美债汇率图表组件
│   ├── BondChart.tsx         # 德债日债图表组件
│   ├── BondChartDebug.tsx    # 德债日债调试组件
│   ├── TimeRangeSelector.tsx # 时间范围选择器
│   ├── LoadingOverlay.tsx    # 加载遮罩组件
│   └── Tabs.tsx              # Tab 切换组件
└── hooks/
    └── useEconomicData.ts    # 数据获取 Hook
```

---

## 功能特性

### 1. Tab 切换

页面提供两个主要 Tab：

| Tab | 说明 | 默认时间范围 | 数据频率 |
|-----|------|-------------|---------|
| 美债汇率 | 美国国债收益率与汇率数据趋势分析 | 3 个月 (3M) | 日级 |
| 德债日债 | 德国和日本国债收益率对比分析 | 1 年 (1Y) | 月级（每月 1 号） |

> **注意**: 德债日债 Tab 中，日本国债目前仅实现 10 年期数据。虽然数据结构中保留 `3m` 和 `2y` 字段，但实际返回空数组（待后续补充数据源）。

### 2. 时间范围选择

支持以下时间范围选项：

| 选项 | 说明 |
|------|------|
| 1M | 最近 1 个月 |
| 3M | 最近 3 个月 |
| 6M | 最近 6 个月 |
| 1Y | 最近 1 年 |
| 3Y | 最近 3 年 |
| 5Y | 最近 5 年 |
| ALL | 全部历史数据（从 2000 年开始） |

### 3. 数据加载策略

**全量加载 + 本地过滤**:

1. 首次加载时获取全部历史数据（从 2000 年开始）
2. 数据缓存在 localStorage（1 小时有效期）
3. 切换时间范围时，前端直接过滤缓存数据，无需重新请求
4. 切换到德债日债 Tab 时，自动过滤为每月 1 号的数据

---

## 组件说明

### EconomicChart (美债汇率图表)

展示美国国债收益率曲线和汇率数据。

**Props**:
- `data: EconomicDataResponse` - 经济数据
- `showAllData?: boolean` - 是否显示全部数据

**展示内容**:
- 美国国债：3 个月期、2 年期、10 年期
- 汇率数据：美元指数、美元兑人民币、美元兑日元、美元兑欧元

### BondChart (德债日债图表)

展示德国和日本国债收益率对比。

**Props**:
- `data: EconomicDataResponse` - 经济数据

**展示内容**:
- 德国国债：3 个月期、2 年期、10 年期
- 日本国债：3 个月期、2 年期、10 年期

### TimeRangeSelector (时间范围选择器)

提供时间范围切换按钮。

**Props**:
- `value: TimeRange` - 当前选中的时间范围
- `onChange: (range: TimeRange) => void` - 时间范围变更回调
- `tabType?: TabType` - 当前 Tab 类型（影响可用选项）

### Tabs (Tab 切换组件)

页面 Tab 切换器。

**Props**:
- `tabs: Tab[]` - Tab 列表配置
- `activeTab: string` - 当前激活的 Tab
- `onTabChange: (tabId: string) => void` - Tab 变更回调

---

## 数据类型

### EconomicDataResponse

```typescript
interface EconomicDataResponse {
  dates: string[];         // 日期数组，格式：YYYY-MM-DD
  us_treasuries: {
    '3m': number[];        // 美国 3 个月期国债收益率
    '2y': number[];        // 美国 2 年期国债收益率
    '10y': number[];       // 美国 10 年期国债收益率
  };
  eu_treasuries: {
    '3m': number[];        // 欧洲 3 个月期国债收益率
    '2y': number[];        // 欧洲 2 年期国债收益率
    '10y': number[];       // 欧洲 10 年期国债收益率
  };
  jp_treasuries: {
    '3m': number[];        // 日本 3 个月期国债收益率
    '2y': number[];        // 日本 2 年期国债收益率
    '10y': number[];       // 日本 10 年期国债收益率
  };
  exchange_rates?: {
    dollar_index: number[];  // 美元指数
    usd_cny: number[];       // 美元兑人民币
    usd_jpy: number[];       // 美元兑日元
    usd_eur: number[];       // 美元兑欧元
  };
}
```

### TimeRange

```typescript
type TimeRange = '1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'ALL';
```

### TabType

```typescript
type TabType = 'treasury-exchange' | 'bonds';
```

---

## Hook 说明

### useEconomicData

获取经济数据的 React Hook。

**参数**:
- `timeRange: TimeRange` - 时间范围
- `tabType: TabType` - Tab 类型（默认：'treasury-exchange'）

**返回值**:
```typescript
{
  data: EconomicDataResponse | null;     // 过滤后的数据
  fullData: EconomicDataResponse | null; // 完整数据
  isLoading: boolean;                     // 是否正在加载
  error: string | null;                   // 错误信息
  isCached: boolean;                      // 是否使用缓存
}
```

**使用说明**:
```typescript
const { data, isLoading, error } = useEconomicData('3M', 'treasury-exchange');
```

---

## 数据流

```
用户访问页面
    ↓
useEconomicData Hook 加载
    ↓
检查 localStorage 缓存
    ├─ 有缓存且未过期 → 使用缓存数据
    └─ 无缓存或已过期 → 调用 API 获取全量数据
    ↓
缓存到 localStorage（1 小时）
    ↓
根据 timeRange 和 tabType 过滤数据
    ↓
传递给图表组件渲染
```

---

## 注意事项

1. **数据频率**:
   - 美债汇率 Tab 使用日级数据
   - 德债日债 Tab 使用月级数据（自动过滤为每月 1 号）

2. **时间范围默认值**:
   - 切换到德债日债 Tab 时，如果当前是 3M，自动切换为 1Y
   - 切换到美债汇率 Tab 时，如果当前是 1Y，自动切换为 3M

3. **图表 Key 生成**:
   - 使用数据的首尾日期作为 Key，确保数据变化时图表组件重新挂载
   - 避免 Plotly 图表因数据长度变化导致的渲染异常

4. **API 路径**:
   - 前端通过 Next.js API Routes 代理请求
   - 路径：`/api/macro/data?start_date=xxx&end_date=xxx`
