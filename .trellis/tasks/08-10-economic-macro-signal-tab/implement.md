# Implement — economic 宏观信号 Tab

> 修订 v3(2026-08-10): 按 demo v2 终稿。GroupCard 替代 DimensionCard;删除 ScoreBadge;卡头双行布局(小字标识 + 20px 加粗 conclusion);指标级 updated_at。

执行顺序严格自底向上:类型 → 常量 → mock → 叶子组件 → 容器 → 接入 page.tsx → 验证。

## Phase A: 类型与契约

- [ ] A1 创建 `apps/economic/src/lib/modules/macro-signal/types.ts`
  - 导出 `DimensionKey`、`MacroIndicator`、`MacroSignalGroup`、`MacroSignalSnapshot`、`MacroSignalTabProps`
  - **不含** score / data_date(已移除)
  - validate: 设计文档 §2.1 逐字段对照
  - validate: `cd apps/economic && pnpm tsc --noEmit` 通过(若有该 script)

- [ ] A2 修改 `apps/economic/src/lib/types/economic.ts` 第 11 行 TabType union
  - 追加 `'macro-signal'`
  - validate: 不动其他类型

## Phase B: 常量与发布规则

- [ ] B1 创建 `apps/economic/src/app/modules/economic/components/macro-signal/constants.ts`
  - 内容: `GROUP_META`(title + order + calendarColor,无评分色)、`INDICATOR_LABELS`(覆盖 demo 列出的全部 21 个 indicator key)
  - validate: 与 demo INDICATOR_LABELS 表逐字段对照

- [ ] B2 创建 `apps/economic/src/lib/modules/macro-signal/release-rules.ts`
  - 实现 `getReleaseDates(month, groupKey): string[]`
  - 实现 `getWorkdayOnOrBefore(y, m, d)` + `getWorkdaysInMonth(y, m)` 辅助
  - validate: `getReleaseDates('2026-05', 'inflation')` 应返回 `['2026-05-10']`(5/10 是周日则前移到 5/09);`getReleaseDates('2026-05', 'monetary_policy')` 应返回该月所有工作日 + 15 日 + 20 日

## Phase C: mock 数据(异步函数)

- [ ] C1 创建 `apps/economic/src/lib/modules/macro-signal/mock-data.ts`
  - 内部 `MOCK_DATA: Record<string, MacroSignalSnapshot>`(month → snapshot),3 个月(2026-03 / 2026-04 / 2026-05)
  - **数据结构与 demo v2 终稿一致**:每个 group = `{ conclusion, indicators: [{key, value, updated_at}] }`
  - 2026-05 conclusion + 指标值直接从 demo 复制
  - 2026-04 / 2026-03:数值 ±10%,updated_at 前移一月,conclusion 调整
  - 2026-03 risk_appetite 设为 `{ conclusion: null, indicators: [] }`
  - 导出 `MOCK_AVAILABLE_MONTHS = ['2026-03', '2026-04', '2026-05']`
  - 导出 `loadMockSnapshot(month): Promise<MacroSignalSnapshot | null>` —— setTimeout 300ms + Promise.resolve(MOCK_DATA[month] ?? null)
  - validate: `await loadMockSnapshot('2026-05')` 拿到非 null;`await loadMockSnapshot('1999-01')` 拿到 null

## Phase D: 叶子组件(自底向上)

- [ ] D1 `GroupCard.tsx`
  - Props: `{ groupKey: DimensionKey; group: MacroSignalGroup; selectedMonth: string }`
  - 卡头第一行:圆点 + 分组名(查 GROUP_META)+ 右侧「N 项指标」
  - 卡头第二行:conclusion(20px 加粗白色)或「数据缺失」(灰色加粗)
  - 指标列表:每行 label(查 INDICATOR_LABELS)+ value(查 digits/unit)+ updated_at
  - value === null → 显示「—」+ 「本月无数据」
  - updated_at 距 selectedMonth 月初 35 天以上 → 黄字 + 「数据偏旧」
  - 整组 indicators 为空 → 列表区显示「本月数据缺失」占位
  - validate: 传入 inflation 的 mock 数据 → 渲染 CPI/PPI/核心CPI 三行 + 「温和」conclusion

- [ ] D2 `GroupCardGrid.tsx`
  - Props: `{ groups: Record<DimensionKey, MacroSignalGroup>; selectedMonth: string }`
  - 按 GROUP_META[*].order 排序,渲染 6 个 GroupCard
  - grid: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4`
  - validate: DOM 上有 6 张卡,顺序正确

- [ ] D3 `MonthSwitcher.tsx`
  - Props: `{ currentMonth; availableMonths; onChange }`
  - 渲染: `<(禁用若到min) [月份下拉] >(禁用若到max)`
  - 月份下拉显示「YYYY 年 M 月」
  - validate: 切到 2026-03 时上一月按钮 disabled

- [ ] D4 `ReleaseCalendar.tsx`
  - Props: `{ month }`(只需月份)
  - 用 release-rules.ts 算出每个分组在该月的发布日期 → 聚合 `{ date: DimensionKey[] }` map
  - 渲染 6×7 周一起始日历,每天画色点(查 GROUP_META[key].calendarColor)
  - 点击单元格 popover 显示当天发布指标列表
  - 今日蓝边框,未来日期 opacity-50
  - validate: 2026-05 月 5/10 CPI/PPI 高亮、5/13 工业增加值等高亮、5/15 MLF 调整日

## Phase E: 容器组件

- [ ] E1 `MacroSignalTab.tsx`
  - Props: `{ loadSnapshot; availableMonths; initialMonth? }`
  - 内部状态:
    - `selectedMonth`(初始 = initialMonth ?? availableMonths 排序后最大值)
    - `snapshot: MacroSignalSnapshot | null`
    - `loading: boolean`
    - `error: string | null`
  - `useEffect([selectedMonth])` → set loading → try `await loadSnapshot(selectedMonth)` → set snapshot 或 null + error → finally set loading false
  - 渲染:
    ```
    <MonthSwitcher ... />
    {loading ? <LoadingSkeletonGrid /> : error ? <ErrorPanel /> : snapshot ? <GroupCardGrid ... /> : <Empty />}
    <ReleaseCalendar month={selectedMonth} />
    ```
  - validate: props 传 loadMockSnapshot + MOCK_AVAILABLE_MONTHS,DOM 上看到 6 张卡 + 月份切换器 + 日历;切月时 loading 占位可见(约 300ms)

## Phase F: 接入 page.tsx

- [ ] F1 修改 `apps/economic/src/app/modules/economic/page.tsx`
  - 顶部加 `import { loadMockSnapshot, MOCK_AVAILABLE_MONTHS } from '@/lib/modules/macro-signal/mock-data';`
  - dynamic import MacroSignalTab
  - tabs 数组追加 `{ id: 'macro-signal', label: '宏观信号', description: '当月 6 维度宏观判断卡片 + 发布日历' }`
  - 在所有 Tab 容器 div 之后加:
    ```tsx
    <div hidden={activeTab !== 'macro-signal'}>
      <MacroSignalTab
        loadSnapshot={loadMockSnapshot}
        availableMonths={MOCK_AVAILABLE_MONTHS}
      />
    </div>
    ```
  - handleTabChange 不需要特判
  - validate: 点击「宏观信号」Tab 能切换,其他 7 个 Tab 切回时状态不丢

## Phase G: 验证

- [ ] G1 lint: `cd apps/economic && pnpm lint` → 通过
- [ ] G2 build: `cd apps/economic && pnpm build` → 通过
- [ ] G3 手动验证(用户跑):
  - 切到「宏观信号」Tab → loading → 6 张分组卡(每张顶部小字标识 + 20px 加粗 conclusion + 指标列表)
  - 切换月份 → loading 占位可见 → 新 conclusion + 新数值
  - 2026-03 市场情绪卡显示「数据缺失」+ 「本月数据缺失」占位
  - 铁路货运量 2026-05 显示「—」+ 「本月无数据」
  - 日历视图正确显示当月发布日期色点,点击弹出 popover
  - 卡片无任何颜色染色,所有 conclusion 用相同样式(20px 加粗白色)

## 回滚点

每个 Phase 是独立 commit 单位。整体推翻时:删 `app/modules/economic/components/macro-signal/` 和 `lib/modules/macro-signal/` 两个目录 + revert page.tsx 与 lib/types/economic.ts 的两处小改。

## 评审 Gate(Phase 1.4)

启动任务前(执行 task.py start)需要用户确认:
- [x] prd.md v3 范围与验收条款(去 score、保留 conclusion、指标级 updated_at)无异议
- [x] design.md v3 Props 契约(`MacroSignalGroup { conclusion, indicators: [{key, value, updated_at}] }`)无异议
- [x] implement.md v3 执行清单 7 个 Phase 无异议

(用户已在前述对话中评审通过,可以 task.py start)
