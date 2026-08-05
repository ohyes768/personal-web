# Design — 挡位监控水平价位条 Tab

## 模块边界

```
backend/dividend-select/
├── src/api/
│   ├── models.py          # AlertLevel + AlertConfigRequest 加 pb 字段
│   └── routes.py          # _alert_config_to_dict 透传 pb
└── (favorites_service.py 不动：dict 字段透传已通用)

apps/dividend/
├── src/
│   ├── lib/
│   │   ├── types.ts        # AlertLevel.pe 已存在，加 pb?: number | null
│   │   ├── api.ts          # 必要时复用现有 dividendApi.getPEData
│   │   └── hooks/
│   │       └── useAlertsStatus.ts  # 乐观更新加 pb 字段
│   ├── components/
│   │   ├── AlertSettingsModal.tsx  # 加 PB 输入框
│   │   └── AlertLevelBar.tsx       # 新建组件（水平价位条）
│   └── app/
│       └── page.tsx        # Tab 加 "挡位监控"，切到时渲染 AlertLevelBar 列表
```

## 数据流

```
启动拉取（已有）：
  page.tsx 加载
  ├── favorites /             (FavoritesService)
  ├── alertsMap               (useAlertsStatus → GET /api/dividend/favorites/alerts/status)
  ├── technicalData            (useTechnicalData → 含 realtime/close/M120)
  └── alertsPEPB               (新增：useAlertsPePb → GET /api/dividend/pe?codes=...)

切换到 Tab 3 (alerts):
  filteredStocks = favorites
    .filter(f => alertsMap[f.code]?.levels 有 ≥1 档非空)

  render <AlertLevelBar> per stock:
    接收 levels (含 PE/PB) + currentPrice + realtimePE/PB
    渲染 5 段色块 + ▲ 三角 + 4 档价格刻度

点击股票行 → 打开 AlertSettingsModal（已有弹窗）
保存 → 乐观更新 hooks → refresh 进入循环
```

## 组件设计

### AlertLevelBar.tsx

```tsx
interface AlertLevelBarProps {
  code: string;
  name: string;
  levels: AlertLevels;          // 4 档价格 + PE/PB
  currentPrice: number;          // 实时价
  currentPE?: number | null;
  currentPB?: number | null;
  prevClose?: number;            // 算涨跌幅
  onClick?: () => void;          // 打开 Modal
}
```

**渲染**：
1. 头部：股票代码 / 名称 / 现价 / 涨跌幅 / 命中状态 badge
2. 区位标签（条上方）：重仓区 / 加仓区 / 持有区 / 减仓区 / 全卖区
3. 5 段色块（条本身）：按 4 档价格归一化百分比切分
4. ▲ 三角指针（条上方）：按当前价归一化百分比定位
5. 4 档价格刻度（条下方）：每档价格 + PE/PB
6. 偏移度行（最底）：每档距离 % 偏离

**计算逻辑**：
```ts
// 4 档价格（含 0 表示未设置）
const prices = [
  { key: 'heavy',  price: levels.heavy_position?.price,  pe: levels.heavy_position?.pe,  pb: levels.heavy_position?.pb },
  { key: 'add',    price: levels.add_position?.price,    pe: levels.add_position?.pe,    pb: levels.add_position?.pb },
  { key: 'reduce', price: levels.reduce_position?.price, pe: levels.reduce_position?.pe, pb: levels.reduce_position?.pb },
  { key: 'full',   price: levels.full_exit?.price,       pe: levels.full_exit?.pe,       pb: levels.full_exit?.pb },
].filter(p => p.price && p.price > 0);

if (prices.length < 2) return null;  // 至少 2 档才能画

const minP = Math.min(...prices.map(p => p.price), currentPrice);
const maxP = Math.max(...prices.map(p => p.price), currentPrice);
const range = maxP - minP || 1;
const pct = (p: number) => ((p - minP) / range) * 100;

// 5 段色块：(0, heavy, add, reduce, full, +∞)
// min 段: ≤ 最小价格
// max 段: ≥ 最大价格
// 中段: 每对相邻价格
```

**命中状态判定**：
```ts
function hitStatus(levels: AlertLevels, currentPrice: number): 'heavy' | 'add' | 'hold' | 'reduce' | 'full' | 'inactive' {
  if (currentPrice <= levels.heavy_position?.price) return 'heavy';
  if (currentPrice <= levels.add_position?.price) return 'add';
  if (currentPrice >= levels.full_exit?.price) return 'full';
  if (currentPrice >= levels.reduce_position?.price) return 'reduce';
  return 'hold';
}
```

### Modal 改动

AlertSettingsModal 在每档价格 + PE 后加 PB 输入框：

```tsx
<label className="flex items-center gap-2 text-sm">
  <span className="text-ink-muted w-12">PB</span>
  <input
    type="number"
    step="0.01"
    min="0"
    placeholder="-"
    value={pbStr}
    onChange={e => updateLevel(key, 'pb', e.target.value)}
    className="bg-paper-card border border-rule rounded px-2 py-1 text-right font-mono text-sm flex-1"
  />
</label>
```

更新 `updateLevel` 函数加 `pb` 字段。

## 状态管理

### page.tsx Tab 切换

```ts
type TabKey = 'all' | 'watchlist' | 'alerts';

const activeTab: TabKey =
  tabParam === 'watchlist' ? 'watchlist' :
  tabParam === 'alerts' ? 'alerts' : 'all';
```

### PE/PB 拉取

```ts
// 新 hook: useAlertsPePb
// 依赖 favorites 列表变化时拉 PE/PB
const { pePbMap, loading: pePbLoading } = useAlertsPePb(favoritesCodes);
```

后端 `/api/dividend/pe?codes=000720,600900,...` 已有，直接用 `dividendApi.getPEData({ codes: codesStr })`。

`getPEData` 返回 `{ items: Array<{code, pe, pb}> }`。

## 兼容性

- **favorites.json 旧数据无 PB**：读时 `dict.get('pb')` 返回 None → Modal 显示空 → 草图色块的 PB 字段显示 `-`
- **下次保存自动写入 PB**：routes `_alert_config_to_dict` 加 PB 字段
- **level 价格字段为 null 时**：不渲染该段（透明度 0）

## 性能

- 30 只股票 × 4 档 = 120 节点计算，毫秒级
- PE/PB 一次请求（30 codes）~ 100ms
- 水平条用绝对定位 CSS（不触发 React 渲染）

## 风险与应对

| 风险 | 应对 |
|------|------|
| PE/PB 缺失 | 显示 `-`，不阻挡渲染 |
| 4 档价格跨度大（如 0.5 vs 600） | 归一化百分比，不按绝对值 |
| currentPrice 超出 4 档范围 | 三角定位在 0% 或 100%，label 显式显示 |
| 边角情况（只有 1 档价格） | 至少 2 档才能画水平条，否则不渲染 |
| Modal 提交后 AlertLevelBar 不刷新 | 复用现有 hooks 乐观更新 + refresh，Monitor 自动反映 |

## 已知遗留

- 持仓监控推钉钉后会不会有状态更新影响 UI：会，但 hooks 走 refresh，Monitor 自动同步
- 移动端：AlertLevelBar 用 flex 布局，< 768px 可能挤——base 看似不需要特别优化，必要时折叠

## 不在本次设计范围

- 移动端深度适配
- 报警历史图表
- 持仓成本 / 盈亏可视化
- 多 Tab 切换动画
