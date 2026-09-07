# 股票基金行点击详情弹框（排名 + 费率）

## Goal

将股票 tab 主表的同类排名 4 列 + 年费列从列表移除，让列表更宽、关键列更突出；同时新增行点击详情抽屉，集中展示同类排名表 + 费率明细。沿用 CompareDrawer 的"右侧抽屉"UX 模式保持视觉一致。

## Background

- 上一个任务 `09-07-stock-fund-rank-display` 已完成：列表新增 4 列排名 + 颜色梯度 + 脚注。**本次回滚**：列表移除 4 排名列 + 1 年费列。
- `FundDetail` 接口已存在（`/api/funds/stock/{code}`），返回 `fees: FundFees` + `achievement_ranks: FundAchievementRank[]`（routes.py:221-242 + services 路径）。
- 前端类型已有 `FundFees` / `FundAchievementRank` / `RankPercentile`（types.ts:32-145）。
- 已存在 `useFeeDetails` hook（hooks.ts:151-181）模式：按 code 批量拉详情合并 fees。
- 已存在 `feeDetailDimensions`（compareDimensions.ts:38-52）——**5 档费率提取模式可直接复用**。
- 已存在 `CompareDrawer`（CompareDrawer.tsx）右侧抽屉风格：fixed right-0 + mask + Escape 关闭 + body overflow hidden + 响应式宽度（xs 95vw → xl 900px）。
- 已有 `@heroicons/react/24/outline`（XMarkIcon 已使用）。
- FundTable 当前**行无 onClick 交互**；按钮（对比）是 row 内的子元素，需避免事件冒泡冲突。
- 已有 `RankColor()` 函数（FundTable.tsx）+ `RANK_PERIODS` 常量（filter_service.py）—— 颜色规则可直接复用。

## User Value

- **列表更宽**：从 17 列回退到 13 列（移除 4 排名 + 1 年费），关键列（代码/名称/类型/规模/年限/经理/收益/风险列）呼吸空间提升。
- **次要信息不丢**：点击行即看完整同类排名表（4 周期 + 历年年度业绩）+ 完整费率明细（4 档赎回 + 申购 + 3 项年费）。
- **复用既有风格**：与 CompareDrawer 一致的右侧抽屉 + 灰底 mask，符合项目 UX 习惯。
- **响应式友好**：移动端 xs 全屏、桌面端固定宽度。

## Requirements

### REQ-1 FundTable：移除 5 列 + 新增行点击

- 移除 `showRankColumns` 块（4 列）+ 移除"年费"列。
- 列顺序回退到：`代码 / 名称 / 类型 / 规模 / 年限 / 回撤 / 经理 / 近1年 / 近3年 / 近5年 / 6 风险列 / 对比`（**债基 tab 仍显示利率债**）。
- **行点击交互**：新增 `onRowClick?: (fund: FundListItem) => void` prop；行 `<tr>` 加 `onClick={onRowClick ? () => onRowClick(fund) : undefined}` + `cursor-pointer`。
- **避免按钮冲突**：对比按钮的 onClick 加 `e.stopPropagation()`，不被行 click 触发。
- 删除 `showRankColumns` prop（如债基 page 也没引用可彻底删）。

### REQ-2 新组件 `RowDetailDrawer`：右侧抽屉展示排名 + 费率

- 路径 `apps/fund-select/src/components/RowDetailDrawer.tsx`。
- 与 CompareDrawer 同款：mask + 右侧 fixed drawer + Escape 关闭 + body overflow 锁定 + 响应式宽度。
- 接口：
  ```ts
  interface RowDetailDrawerProps {
    fund: FundListItem | null;       // null = 关闭
    onClose: () => void;
  }
  ```
- 内部：`fund` 变化时按 `stockApi.getDetail(fund.code)` 拉详情；拉取期间显示**骨架屏**（用户决策）；失败显示 `-`。
- 抽屉内容布局（自上而下）：
  1. **头部**：基金代码 + 名称 + 关闭按钮
  2. **同类排名表 1**：`4 周期排名`（今年来 / 近1年 / 近3年 / 近5年）
     - 列：周期 | 收益 | 百分位 chip | 同类排名/总数
     - 数据源：`achievement_ranks` 里 `period_kind ∈ {年度业绩, 阶段业绩} ∧ period ∈ {今年以来, 近1年, 近3年, 近5年}`，按 RANK_PERIODS 顺序展示
  3. **同类排名表 2**：`历年年度业绩`（**完整展示**，含成立以来 + 今年以来 + 历年数字年份）
     - 列：年份 | 收益 | 百分位 chip | 同类排名/总数
     - 数据源：`period_kind=年度业绩 ∧ period` 为数字年份或"成立以来"/"今年以来"，按年份倒序（数字年份 desc；"今年以来"与最新年份相邻；"成立以来"末位）
     - 收益正负染色
  4. **费率明细表**：
     - 列：项目 | 费率
     - 行：申购费(小额档) / 赎回 <7天 / 赎回 7天~1年 / 赎回 ≥1年 / 赎回 ≥7天 / 管理费 / 托管费 / 销售服务费 / **年费合计**（mgmt + custody + service）
     - 缺失字段显示 `-`

### REQ-3 stock page：行点击触发抽屉

- 在 stock/page.tsx 引入 RowDetailDrawer。
- 本地 state：`const [detailFund, setDetailFund] = useState<FundListItem | null>(null)`。
- 传 `<FundTable onRowClick={setDetailFund} ... />` 和 `<RowDetailDrawer fund={detailFund} onClose={() => setDetailFund(null)} />`。
- 债基 page **不引入**（无对应数据源；用户决策"仅股票"）。

### REQ-4 移除上一任务的列表展示

- 删除 `apps/fund-select/src/app/stock/page.tsx` 中 `showRankColumns` 传参。
- FundTable 删除 `showRankColumns` prop、`RANK_TIPS`、`rankColor()`、`RankChip` 相关代码。
- globals.css `--color-rank-*` token **保留**（抽屉内还要用；不删）。
- 后端 `rank_ytd / rank_1y / rank_3y / rank_5y` 字段**保留**（DTO 契约 + 向后兼容）。

### REQ-5 测试

- 前端无单测框架，沿用 tsc + build + 手动截图。
- 后端不动（DTO 字段保留），回归测试预期 171 passed 不变。

## Acceptance Criteria

| ID | 标准 | 映射 REQ |
|---|---|---|
| AC-1 | 股票 tab FundTable 主表列数回退至 12 列（不含对比）；移除 4 排名列 + 1 年费列；不再出现"排名·..."列头 | REQ-1, REQ-4 |
| AC-2 | 行 `<tr>` 有 `cursor-pointer` + onClick；点击对比按钮不触发行 click（stopPropagation 生效） | REQ-1 |
| AC-3 | 点击任意一行 → 右侧抽屉滑出；mask 半透明黑；Escape 关闭；body overflow 锁定 | REQ-2 |
| AC-4 | 抽屉头部显示基金代码 + 名称 | REQ-2 |
| AC-5 | 抽屉第一张表展示"4 周期排名"：`今年来 / 近1年 / 近3年 / 近5年`，每行有周期/收益/百分位 chip/原始排名 4 列；缺失字段 `-` | REQ-2 |
| AC-6 | 抽屉第二张表展示"历年年度业绩"：**完整展示**（含成立以来 + 今年以来 + 历年数字年份），按倒序，含收益/百分位/原始排名；正收益绿、负收益红 | REQ-2 |
| AC-7 | 抽屉第三张表展示"费率明细"：申购小额档 / 4 档赎回 / 3 项年费 + 年费合计；缺失 `-` | REQ-2 |
| AC-8 | 关闭抽屉（Escape / mask / 关闭按钮）回到列表，列表状态保留（筛选 / 排序不动） | REQ-2, REQ-3 |
| AC-9 | 移动端（xs < 640px）：抽屉全屏 95vw；桌面端（xl ≥ 1280px）：900px | REQ-2 |
| AC-10 | 债基 tab FundTable **完全不动**（不引入行 click、不引入抽屉）；后端 DTO 字段保留向后兼容 | REQ-3, REQ-4 |
| AC-11 | 后端 pytest 171 passed（不动后端，回归保护） | REQ-5 |
| AC-12 | 前端 `pnpm tsc --noEmit` 通过；`pnpm build` 因 standalone EPERM 与本任务无关（既有） | REQ-5 |
| AC-13 | 截图：列表列宽对比、抽屉展开（4 周期 + 年度业绩 + 费率明细）、移动端全屏 | REQ-5 |
| AC-14 | `--color-rank-*` token 保留（抽屉复用） | REQ-4 |
| AC-15 | 抽屉内点击 row click 后**骨架屏**渲染（用户决策），数据返回后填充 | REQ-2 |

## Non-Goals

- ❌ 不新增 Dialog 组件库；沿用 CompareDrawer 风格手写。
- ❌ 不做"详情页路由 `/funds/stock/{code}`"；弹框是叠加层。
- ❌ 不在弹框里展示业绩走势 / 持仓 / 经理详情 / 风险指标等（用户决策"仅排名 + 费率"）。
- ❌ 不改债基 tab。
- ❌ 不改后端 DTO / 数据源（沿用 09-07-stock-fund-rank-display 的 `_parse_peer_rank` + `RANK_PERIODS`）。
- ❌ 不做"按排名排序" / "自然月排名"（上任务 deferred）。

## Technical Notes

- 复用 `filter_service.py` 的 `RANK_PERIODS = [(年度业绩, 今年以来, rank_ytd), ...]`，前端可直接镜像。
- 抽屉样式参考 `CompareDrawer.tsx:48-82`：mask + fixed top-0 right-0 bottom-0 + 响应式宽度。
- 详情加载：`useEffect` 监听 `fund?.code`，调 `stockApi.getDetail(code)`；清理用 `cancelled` 标志（hooks.ts:165 模式）。
- 列表的 `fee_annual` / `fee_mgmt` / `fee_custody` / `fee_service` 字段**保留**（DTO 契约 + CompareDrawer 用 `fee_annual` 维度），只是列表不展示。
- 列表的 `rank_ytd / rank_1y / rank_3y / rank_5y` 字段**保留**（向后兼容，DTO 不动）。
- 历年年度业绩排序逻辑：
  ```ts
  function sortAnnualRanks(ranks: FundAchievementRank[]): FundAchievementRank[] {
    return ranks.filter(r => r.period_kind === '年度业绩')
      .sort((a, b) => {
        if (a.period === '成立以来') return 1;
        if (b.period === '成立以来') return -1;
        if (a.period === '今年以来') return -1;
        if (b.period === '今年以来') return 1;
        return Number(b.period) - Number(a.period);
      });
  }
  ```
- 4 周期排名顺序硬编码与后端 RANK_PERIODS 对齐：`(年度业绩, 今年以来, rank_ytd) → (阶段业绩, 近1年) → (阶段业绩, 近3年) → (阶段业绩, 近5年)`。

## Risks / Rollback

- 风险 1：用户对"行 click"误触发对比 → 已加 `e.stopPropagation()` 隔离对比按钮。
- 风险 2：详情请求失败 → 抽屉内显示"加载失败"提示 + 关闭按钮，不阻塞列表。
- 风险 3：列表列宽回退导致某些列变宽（无内容挤压）→ 1280px 屏幕应自然吸收。
- 风险 4：抽屉宽度与 CompareDrawer 冲突（如同时打开）→ 业务上不会同时打开（先关 CompareDrawer 才能点行），可不处理；如发生则后开者覆盖。
- 回滚步骤：
  1. 还原 FundTable 列（恢复 4 排名列 + 1 年费列 + showRankColumns prop）。
  2. 删除 RowDetailDrawer 组件。
  3. 还原 stock/page.tsx（移除 onRowClick 传参 + RowDetailDrawer 引入）。
