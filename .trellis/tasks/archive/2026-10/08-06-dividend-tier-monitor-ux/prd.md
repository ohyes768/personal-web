# 分析并优化股息率挡位监控

## Goal

让 `apps/dividend` 的「挡位监控」Tab 在视觉密度、色彩语义、反馈时效和暖白主题融入四个维度上达到「一眼看懂」的可读性 —— 一屏可扫描多只股票、色条方向感与价格方向感一致、配置过程所见即所得。

## Background

### 最近 6 次提交（git log apps/dividend）

| commit | 摘要 |
|---|---|
| `0ebaeda` | feat(dividend/alerts): 前端集成挡位监控 UI + bump dividend-select |
| `99e8d58` | feat(dividend/alerts): 挡位设置弹框加「立即扫描全部挡位」按钮 |
| `de0b1f1` | feat(dividend): 指数持仓状态改 popover 下拉 + 修复挡位铃铛默认色隐形 |
| `ba0cd15` | feat(dividend): 前端集成 8 个红利指数刷新徽章 |
| `ae731e9` | refactor(dividend/ui): 挡位设置弹框精简（去元数据 + 加 updated_at 展示） |
| `d46b53b` | feat(dividend/ui): 挡位监控 Tab（水平价位条 + 5 段色块 + ▲ 三角 + PE/PB） |

### 核心组件

- `apps/dividend/src/components/AlertLevelBar.tsx:1`（292 行，核心可视化）
- `apps/dividend/src/components/AlertSettingsModal.tsx:1`（323 行，配置入口）
- `apps/dividend/src/lib/hooks/useAlertsStatus.ts:1`（Hook，乐观更新 + 跨 tab 同步）
- `apps/dividend/src/app/page.tsx:1071-1107`（Tab 列表渲染入口）
- `apps/dividend/public/alerts-preview.html:1`（v3 设计稿，已和最终实现脱钩）

## Confirmed Facts

- **6 次迭代演化形成**：档位 UI 从无到 5 段色条 + PE/PB + 实时命中徽章。
- **`hitStatus()` 逻辑**：AlertLevelBar.tsx:66-76，heavy→add→full→reduce 顺序检测当前价落在哪一档。
- **5 段色块**：AlertLevelBar.tsx:42-47，绿（重仓）/ 黄（加仓）/ 灰（持有）/ 橙（减仓）/ 红（全卖），色条背景 `bg-slate-700`。
- **PE/PB 重复 5 次**：4 档刻度各一次（AlertLevelBar.tsx:259-263）+ 当前价一次（230-235 行）。
- **Tab 数量徽章缺失**：page.tsx:1047-1051「挡位监控」Tab 无数量徽章。
- **距离行阈值**：AlertLevelBar.tsx:279 `isNear = Math.abs(pct) < 10`，10% 内全部染黄。
- **暖白主题已落地**：commit `a42e32d` 切换 `bg-paper-card` / `text-ink` 系；AlertLevelBar 仍用 `bg-slate-700` 色条背景，**主题割裂**。
- **alerts-preview.html** 设计稿用了暗色背景（`#0f172a`），与最终暖白实现脱钩。

## Resolved Decisions（已锁定）

- **D1 范围**：全套 P0-P2 优化（用户 2026-08-06 拍板"选 C"）
- **D2 色彩语义**：B 方案 — 色条只表达"价格区间"（4 段渐变），命中徽章单独表达"操作建议"，两层信息分通道单一职责
- **D3 命中徽章措辞**：A 方案 — 🟢 可加仓 / 🟡 加仓价位 / 🟠 该减仓 / 🔴 全部清仓 / ⏸ 持有观望
- **D4 Modal 实时预览形态**：A 方案 — 抽独立 `<AlertLevelBarMini />` 组件，Modal 底部加迷你色条 + 4 个 ▲ 标记

## Requirements

### P0 — 立即消除「不直观」根因

- **REQ-P0-A 信息密度压缩**：AlertLevelBar 卡片从 5 层压到 3 层（头/色条+指针/刻度）。4 档刻度去掉 PE/PB 列；当前价 PE/PB 保留。
- **REQ-P0-B 色彩通道解耦**：
  - 色条从 5 段重画为 **4 段 + 浅灰背景**（对应 4 档价格切分），渐变方向左低右高，颜色从"绿→黄→橙→红"按价格递增。
  - 命中徽章（"重仓命中"等）改为操作动词（见 D3）。
  - 删除"持有区"独立色块——持有状态由徽章 `⏸ 持有观望` + 距离行表达，不再占独立色段。
- **REQ-P0-C ▲ 标签溢出处理**：当前价 ¥xx.xx 标签在 pct≈0/100 时不出卡片边界（用 left: clamp(min, max) 模式而非简单 translateX(-50%))。

### P1 — Tab 与反馈链路

- **REQ-P1-A 数量徽章**：page.tsx:1047-1051「挡位监控」Tab 加 `{alertStocks.length}` 徽章。
- **REQ-P1-B 距离行三级色阶**：`<5%` 红 / `5-10%` 黄 / `>10%` 默认灰，替代当前两级。
- **REQ-P1-C Modal 实时命中预览**：抽 `<AlertLevelBarMini />` 独立组件（4 个 ▲ 标记 + 4 段色条 + 无当前价 ▲），Modal 底部渲染，4 档价格任意变化实时重渲染。

### P2 — 主题融入

- **REQ-P2-A 暖白主题色块适配**：色条背景 `bg-slate-700` → `bg-paper-deep`；4 段色块用低饱和暖色调（绿 `#16a34a`/ 黄 `#ca8a04` / 橙 `#ea580c` / 红 `#dc2626`），保持颜色方向感但降饱和度避免刺眼。
- **REQ-P2-B 命中徽章暖白适配**：徽章底色从 `bg-{color}-900/50` 深色半透 → `bg-{color}-50 text-{color}-700 border-{color}-200`（如 `bg-green-50 text-green-700 border-green-200`），匹配全局暖白色板。

## Acceptance Criteria

- [ ] AC-1 挡位监控 Tab 显示已设挡位股票数量（徽章值 = alertStocks.length）
- [ ] AC-2 AlertLevelBar 卡片高度比当前减少 ≥ 30%（密度优化验证）
- [ ] AC-3 色条方向与价格方向严格一致：从左到右价格递增，颜色由低饱和绿→黄→橙→红过渡；不再有"持有区"独立色块
- [ ] AC-4 当前价 ¥xx.xx 标签在 pct=0% 与 pct=100% 时不出卡片边界（视觉验证）
- [ ] AC-5 距离行三级色阶生效：`<5%` 红色字 / `5-10%` 黄色字 / `>10%` 默认灰字
- [ ] AC-6 Modal 输入 4 档价格时，底部迷你色条 4 个 ▲ 标记位置实时变化（视觉验证）
- [ ] AC-7 暖白主题下色条与卡片背景对比度合理，无"暗色贴片"割裂感
- [ ] AC-8 命中徽章文案统一为：「🟢 可加仓 / 🟡 加仓价位 / 🟠 该减仓 / 🔴 全部清仓 / ⏸ 持有观望」
- [ ] AC-9 命中徽章在暖白主题下文字与背景对比度满足 WCAG AA（色阶从 -900 改为 -50/-700/-200 组合）
- [ ] AC-10 视觉验收：dashboard 在 1440×900 分辨率下，挡位监控 Tab 一屏可见 ≥ 5 只股票卡片
- [ ] AC-11 `pnpm build` 与 `pnpm lint` 通过，无新增 TS 错误
- [ ] AC-12 钉钉推送文案（后端 `dividend-select/src/services/alert_service.py` 同位置）同步更新为新措辞，避免推送内容与前端不一致

## Technical Notes

- **不改动**：`useAlertsStatus.ts` Hook（乐观更新+回滚+跨tab同步是稳态的）；后端 API 契约；`usePEData` 数据源。
- **新建组件**：`apps/dividend/src/components/AlertLevelBarMini.tsx`（D4 决定抽独立组件，避免 Modal 复用主组件时的 props 耦合）。
- **暖白色板 token**：`bg-paper-card` / `bg-paper-deep` / `text-ink` / `text-ink-muted` / `border-rule` / `border-rule-strong` 均已在 `apps/dividend/src/app/globals.css` 定义。
- **钉钉推送文案同步**：`dividend-select/src/services/alert_service.py`（具体路径以实际为准）需要同步改 4 个档位的文案，与前端 HIT_META 表对齐。
- **alerts-preview.html**：保留但加注释说明已脱钩（用户已确认 2026-08-06）。

## Out of Scope

- 重新设计 4 档价格语义本身（重仓/加仓/减仓/全卖）
- 修改后端钉钉推送规则或扫描调度
- 修改 `useAlertsStatus` 的乐观更新逻辑
- 新增 PE/PB 趋势曲线或历史图表
- 移动端独立 UI（继续走响应式兼容）
- 删除 `alerts-preview.html` 文件

## Open Questions

无 — 所有产品决策已锁定（D1/D2/D3/D4）。