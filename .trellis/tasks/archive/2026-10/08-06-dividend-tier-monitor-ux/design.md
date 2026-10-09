# 设计文档：股息率挡位监控 UX 优化

## 1. 范围

仅 `apps/dividend` 前端 + 同步后端钉钉推送文案。不改后端 API，不改 Hook 状态机。

## 2. 信息架构（IA）

### 2.1 当前 IA（5 层堆叠，不直观）

```
L1  股票头（代码/名/现价/涨幅/命中徽章）
L2  5 个区位标签（重仓区/加仓区/持有区/减仓区/全卖区）
L3  5 段色条 + ▲ 三角 + 当前价标签（PE/PB）
L4  4 档价格刻度（tag+价格+PE/PB）—— PE/PB 重复 4 次
L5  距离行（4 个百分比，10% 内全染黄）
```

### 2.2 目标 IA（3 层通道单一职责）

```
L1  股票头（代码/名/现价/涨幅/操作建议徽章）       ← 通道 A：决策
L2  4 段色条（价格区间） + ▲ 三角（当前价+PE/PB）   ← 通道 B：位置
L3  4 档价格刻度（tag+价格，无 PE/PB）+ 距离行      ← 通道 C：参考
```

**通道职责**：
- **通道 A 决策**：徽章直白动词，「可加仓 / 加仓价位 / 该减仓 / 全部清仓 / 持有观望」
- **通道 B 位置**：色条只标"价格在哪一档"，4 段渐变（左低右高）；当前价 ▲ 不带 PE/PB 重复
- **通道 C 参考**：刻度价格 + 距离行（4 个百分比）

## 3. 视觉规范

### 3.1 色板（暖白主题适配）

```
色条背景   bg-paper-deep    (#F4F1EC 类)
色段（4 段） 低饱和暖色
  重仓区  #16A34A  (green-600)
  加仓区  #CA8A04  (yellow-600)
  减仓区  #EA580C  (orange-600)
  全卖区  #DC2626  (red-600)
持有区     无独立色段，由背景浅灰表达 + 徽章 ⏸ 持有观望
当前价 ▲  #4F46E5  (indigo-600，沿用主品牌色)
```

### 3.2 命中徽章暖白配色

```
🟢 可加仓        bg-green-50  text-green-700  border-green-200
🟡 加仓价位      bg-yellow-50 text-yellow-700 border-yellow-200
🟠 该减仓        bg-orange-50 text-orange-700 border-orange-200
🔴 全部清仓      bg-red-50    text-red-700    border-red-200
⏸ 持有观望      bg-slate-50  text-slate-600  border-slate-200
```

### 3.3 距离行三级色阶

```
<5%   红色字  + ✓ 标记（已命中或极近）
5-10% 黄色字
>10%  默认灰
```

### 3.4 几何规则

- 卡片高度：从当前 ~280px 压到 ~180px（-35%）
- 色条高度：10px（原 8px）
- 刻度下间距：8px（原 14px，去掉 PE/PB 行后空间足够）
- 当前价 ¥xx.xx 标签：水平位置 `clamp(8%, pct(currentPrice), 92%)`，避免贴边
- ▲ 三角：水平位置跟随 clamp 后的 left%

## 4. 组件边界

### 4.1 改动文件清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `apps/dividend/src/components/AlertLevelBar.tsx` | 重构 | 5 段→4 段色条 / 徽章措辞 / 距离行 3 级 / 标签溢出处理 |
| `apps/dividend/src/components/AlertLevelBarMini.tsx` | 新建 | Modal 用的迷你版（无当前价 ▲，4 个 ▲ 标记） |
| `apps/dividend/src/components/AlertSettingsModal.tsx` | 改动 | 引入 AlertLevelBarMini，底部加实时预览 |
| `apps/dividend/src/app/page.tsx` | 微调 | 挡位监控 Tab 加 `{alertStocks.length}` 徽章 |
| `apps/dividend/public/alerts-preview.html` | 加注释 | 标注已脱钩（不动结构） |
| `backend/dividend-select/src/services/alert_service.py` | 改文案 | 同步钉钉推送的 4 档措辞（具体路径以实际为准） |

### 4.2 不改文件

- `apps/dividend/src/lib/hooks/useAlertsStatus.ts` — 状态机已稳态
- `apps/dividend/src/lib/types.ts` — AlertLevels / AlertLevel 类型不变
- `apps/dividend/src/lib/watchlist.ts` — API 客户端不变
- 后端 API 路由 + Pydantic 模型

## 5. 关键算法

### 5.1 AlertLevelBarMini 的 4 个 ▲ 定位

```ts
// 与 AlertLevelBar 共享归一化逻辑
function pct(price: number, minP: number, maxP: number) {
  const range = maxP - minP || 1;
  return Math.max(0, Math.min(100, ((price - minP) / range) * 100));
}
// 4 档价格按升序排序，每档一个 ▲
// 不画当前价 ▲（用户场景是"还没设完成，没有现价"）
```

### 5.2 当前价 ▲ 标签溢出处理

```tsx
const markerLeft = pct(currentPrice);
// 标签文字宽度 ~50px，卡片宽 ~600px，8% ≈ 48px
const clampedLeft = Math.max(8, Math.min(92, markerLeft));
```

### 5.3 距离行三级色阶

```ts
function distTone(pct: number, isHit: boolean): string {
  if (isHit || Math.abs(pct) < 5) return 'text-red-500 font-semibold';
  if (Math.abs(pct) < 10) return 'text-yellow-600';
  return 'text-ink-muted';
}
```

## 6. 兼容性与回滚

- 暖白配色改了，但 5 段色块的 `bg-green-500` 等类名只是替换为低饱和 hex 值；不影响 Tailwind JIT 编译。
- 新增 `AlertLevelBarMini` 是纯新增组件，不影响任何已有引用。
- 钉钉推送文案同步改 — 如推送侧遗漏，前端会显示新文案、推送发旧文案，不影响业务功能（仅文案不一致）。
- 回滚点：单 commit `feat(dividend/ui): 优化挡位监控 UX（密度+色彩+预览）`，可整体 revert。

## 7. 数据流不变

```
useAlertsStatus.status.items
  ↓ alertMap.get(code)
  ↓ AlertStatusItem.levels  → AlertLevels (4 档价格+PE+PB)
  ↓ AlertLevelBar 接收
  ↓ 色条归一化百分比 + ▲ 定位

dividendApi.getPEData(code) → pePbMap[code] → 当前价 PE/PB
```

API 与数据流完全不变，只是渲染层做了减法和信息分层。

## 8. 与已有组件的耦合度

- AlertLevelBarMini 必须复用 AlertLevelBar 的 `pct()` 归一化函数 — 抽到 `lib/levels.ts`（暂不抽，等用 2 次以上再抽；当前只用 1 次，inline 即可）
- 命中徽章 HIT_META 字典两边都需要 — AlertLevelBar 与 AlertLevelBarMini 各自定义（数据量小，不抽）
- Modal 引入 AlertLevelBarMini 后 props 透传：levels + 4 档价格 + onChange 回调