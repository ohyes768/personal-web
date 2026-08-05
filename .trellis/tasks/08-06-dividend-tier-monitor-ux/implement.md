# 执行计划：股息率挡位监控 UX 优化

## 1. 顺序（按依赖排序）

```
Step 1: 改 AlertLevelBar（主组件）
  ↓
Step 2: 新建 AlertLevelBarMini
  ↓
Step 3: 改 AlertSettingsModal（引入 Mini）
  ↓
Step 4: 改 page.tsx（Tab 数量徽章）
  ↓
Step 5: 同步后端钉钉推送文案
  ↓
Step 6: alerts-preview.html 加脱钩注释
  ↓
Step 7: 验证（lint / build / 视觉）
```

## 2. 详细步骤

### Step 1 — AlertLevelBar 重构（核心文件）

**文件**：`apps/dividend/src/components/AlertLevelBar.tsx`

**改动清单**：

1. **L26-31 LEVEL_META**：保留（这是单档信息字典，仅 D3 改徽章措辞）

2. **L33-39 ZONE_LABELS**：删除 5 个区位标签（"重仓区/加仓区/持有区/减仓区/全卖区"）—— 不再需要独立显示

3. **L41-47 ZONE_SEGMENT_CLASS**：5 段色块改为 4 段
   - 删除 `hold: 'bg-slate-500'`
   - 4 段顺序：heavy(绿) / add(黄) / reduce(橙) / full(红)
   - 类名改用低饱和 hex inline style（避免 Tailwind JIT 漏扫）：
     ```ts
     const SEG_COLORS = {
       heavy: '#16A34A',
       add: '#CA8A04',
       reduce: '#EA580C',
       full: '#DC2626',
     };
     ```

4. **L49-55 ZONE_SEGMENT_OPACITY**：删除 hold 段，统一 opacity-90

5. **L66-76 hitStatus**：逻辑不变（已稳态），但持有时返回 'hold'（用于徽章显式）

6. **L78-85 HIT_META**：
   ```ts
   const HIT_META: Record<HitStatus, { label: string; cls: string } | null> = {
     heavy:  { label: '🟢 可加仓',     cls: 'bg-green-50 text-green-700 border border-green-200' },
     add:    { label: '🟡 加仓价位',   cls: 'bg-yellow-50 text-yellow-700 border border-yellow-200' },
     reduce: { label: '🟠 该减仓',     cls: 'bg-orange-50 text-orange-700 border border-orange-200' },
     full:   { label: '🔴 全部清仓',   cls: 'bg-red-50 text-red-700 border border-red-200' },
     hold:   { label: '⏸ 持有观望',    cls: 'bg-slate-50 text-slate-600 border border-slate-200' },
     inactive: null,
   };
   ```

7. **L121-139 segments**：从 5 段重算为 4 段
   ```ts
   // 4 段：4 个相邻价格对 (p0,p1)(p1,p2)(p2,p3) + 两侧 [minP,p0][p3,maxP]
   // 但视觉上只显示中间 3 段有意义色 + 两侧浅灰底
   // 简化方案：直接画 4 段有色色块（与 5 段相比去掉了 hold 段，前后两段保留绿色/红色）
   // 重写为：4 段有色色块 + 2 段浅灰背景（minP→p0、p3→maxP）
   ```

8. **L162-291 JSX**：
   - 删除 L186-201 的 5 个区位标签 DOM
   - 色条背景改为 `bg-paper-deep`
   - 当前价 ▲ 标签的 left 用 clamp：
     ```tsx
     const clampedLeft = Math.max(8, Math.min(92, pct(currentPrice)));
     ```
   - L240-267 刻度部分：删除 PE/PB 两行
   - L270-289 距离行：3 级色阶（<5% 红 / 5-10% 黄 / >10% 默认灰）

### Step 2 — 新建 AlertLevelBarMini

**文件**：`apps/dividend/src/components/AlertLevelBarMini.tsx`（新建）

**接口**：
```ts
interface AlertLevelBarMiniProps {
  levels: AlertLevels;
}
```

**结构**：
- 高度 24px 的迷你色条
- 4 个 ▲ 标记按 4 档价格归一化定位
- 无当前价 ▲（Modal 里没有现价场景）
- 复用 AlertLevelBar 的 pct() 函数（暂时 inline，不抽 lib）

### Step 3 — AlertSettingsModal 引入 Mini

**文件**：`apps/dividend/src/components/AlertSettingsModal.tsx`

**改动**：
1. 顶部 import 加入 `AlertLevelBarMini`
2. 在 L181 `space-y-4` 容器内，4 档价格表（L199-258）下方、启用 checkbox（L261-269）上方，插入：
   ```tsx
   <div className="border border-rule rounded p-3 bg-paper-tint">
     <div className="text-[11px] text-ink-muted mb-2">实时预览</div>
     <AlertLevelBarMini levels={validLevels} />
   </div>
   ```
3. 4 档价格输入的 onChange 已有 updateLevel，validLevels 通过 useMemo 计算（L116-127），变化时自动触发 Mini 重渲染

### Step 4 — page.tsx 加 Tab 徽章

**文件**：`apps/dividend/src/app/page.tsx`

**改动**：L1050 后插入：
```tsx
{alertStocks.length > 0 && (
  <span className="ml-1 text-xs bg-gray-700 px-1.5 py-0.5 rounded">
    {alertStocks.length}
  </span>
)}
```

### Step 5 — 后端钉钉推送文案同步

**文件**：`backend/dividend-select/src/services/alert_service.py`（具体路径以实际代码为准）

**改动**：找到推送模板中 4 档的措辞（旧："重仓命中/加仓命中/减仓命中/全部清仓"），改为新文案（"可加仓/加仓价位/该减仓/全部清仓"）。

**注**：如果 alert_service.py 文案是从前端常量表（已通过 API 返回）的，保持不变即可；只有硬编码在 .py 里的需要改。

### Step 6 — alerts-preview.html 加注释

**文件**：`apps/dividend/public/alerts-preview.html`

**改动**：在 `<title>` 后加一行注释：
```html
<!-- 此为 2026-08-05 之前的设计稿 v3，与最终暖白实现已脱钩，仅作历史参考。详见 .trellis/tasks/08-06-dividend-tier-monitor-ux/ -->
```

### Step 7 — 验证

```bash
# 进入前端目录
cd apps/dividend

# 类型检查 + 构建
pnpm build

# Lint
pnpm lint

# 启动 dev 服务器，访问 ?tab=alerts
pnpm dev
# 浏览器人工验证：
#   1. Tab 数量徽章显示
#   2. 卡片密度（高度 -30%）
#   3. 色条 4 段渐变（无灰色持有段）
#   4. 边界价格时 ▲ 标签不出框
#   5. 距离行 3 级色阶
#   6. Modal 打开后输入价格 → 实时预览变化
```

## 3. 验证清单（AC 对照）

| AC | 验证方式 | 步骤 |
|---|---|---|
| AC-1 数量徽章 | 视觉 | Step 4 |
| AC-2 卡片高度 -30% | DevTools 量高度 | Step 1 |
| AC-3 4 段色条无持有区 | 视觉 | Step 1 |
| AC-4 ▲ 不溢出 | 设极低价/极高价股票 | Step 1 |
| AC-5 距离 3 级色 | 视觉 | Step 1 |
| AC-6 Modal 实时预览 | 输入价格看 Mini 变化 | Step 3 |
| AC-7 暖白融入 | 视觉 | Step 1 |
| AC-8 徽章措辞新文案 | 全局 grep | Step 1 |
| AC-9 暖白对比度 | DevTools 对比度检查 | Step 1 |
| AC-10 5 只/屏 | 1440×900 视口 | Step 7 |
| AC-11 lint/build | 终端 | Step 7 |
| AC-12 钉钉推送同步 | grep 后端 | Step 5 |

## 4. 高风险点

- **R1**：色块改 inline hex 后，可能与 Tailwind 的 `bg-paper-deep` 等 token 冲突 → 改用 CSS 变量定义在 globals.css
- **R2**：抽 AlertLevelBarMini 时复用 pct() 函数，临时 inline → 后续如多处用再抽 lib/levels.ts
- **R3**：钉钉推送文案修改需看后端 alert_service.py 实际结构 — 后端代码是 submodule，可能不是简单字符串替换

## 5. 回滚点

单 commit `feat(dividend/ui): 优化挡位监控 UX（密度+色彩+预览）`，所有改动在 1 个 commit 内；可 `git revert <sha>` 整体回滚。

## 6. 完成检查清单

- [ ] prd.md 已收敛（无重复事实）
- [ ] design.md / implement.md 已写
- [ ] 7 步全部完成
- [ ] 12 个 AC 全部通过
- [ ] 单 commit 完成
- [ ] 任务归档到 `.trellis/tasks/` 完成目录