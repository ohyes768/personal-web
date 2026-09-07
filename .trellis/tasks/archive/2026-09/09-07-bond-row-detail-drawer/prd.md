# 债基 tab 行点击详情抽屉（持仓 + 费率）

## Goal

让债基 tab 主表更简洁（移除年费列），新增行点击详情抽屉集中展示**持仓分析 + 费率明细**。持仓用券种饼图可视化（利率 / 信用 / 可转债）+ 前五大集中度 + 前五大债券明细；费率与股票抽屉同款。

## Background（已确认事实）

- 上一个任务 `09-07-stock-row-detail-dialog` 已完成：FundTable 新增 `onRowClick` prop + 行 onClick + 按钮 stopPropagation；股票 tab 引入 RowDetailDrawer（mask + 右侧抽屉 + 3 张表）。
- 债基 `FundDetail.holdings` 字段已存在（types.ts:60-69）：`rate_bond_pct / credit_bond_pct / convertible_pct / top5_concentration / top5_bonds / report_date`。
- 后端持仓 ETL `analyze_holdings()`（holdings_fetcher.py:64-88）输出标准 dict；债基 refresh 路径写入 `fund_holdings_bond` 表（refresh_service.py:91-93）。
- 实测 `GET /api/funds/217022` 返回 holdings 完整数据（`rate_bond_pct=2.6 / credit_bond_pct=14.1 / convertible_pct=0.0 / top5_concentration=16.7 / top5_bonds="21民生银行永续债01(6.8%); ..."`）。
- 债基 `achievement_ranks` 永远为空（refresh_service.py:97-106 不抓债基）。
- 债基 FundTable 当前 14 列：代码 / 名称 / 类型 / 规模 / 年限 / 回撤 / 经理 / 近1年 / 近3年 / 近5年 / 利率债 / 年费 / 对比（含利率债专列）。
- 已有 `RowDetailDrawer.tsx`（股票 tab）可参考风格。
- `@heroicons/react/24/outline` XMarkIcon 已使用。
- 后端 0 改动。

## User Value

- **列表更宽**：14 列 → 13 列（移除年费列），与股票 tab 保持同步。
- **债基特色信息集中**：持仓分析（券种饼图 + 集中度 + 前五大债券明细）是债基独有的核心信息，在抽屉内一屏可览。
- **可视化辅助**：券种饼图直观展示利率/信用/可转债暴露程度，比纯数字更易判断风险偏好。
- **视觉一致**：与股票抽屉同款 mask + 右侧 fixed + Escape。

## Requirements

### REQ-1 FundTable：移除"年费"列

- 删除 FundTable 的"年费"列 th 和 td（之前 stock tab 已删过，现在同步债基 tab）。
- FundTableProps 不引入新 prop；现有 `onRowClick` 已存在并复用。
- 删完后 FundTable 不再引用 `fund.fee_annual` 列。
- 债基 page `showBondColumns={true}` 仍显示利率债列；列表从 14 列 → 13 列。

### REQ-2 新建 `RowDetailDrawerBond`：右侧抽屉 2 张表

- 路径 `apps/fund-select/src/components/RowDetailDrawerBond.tsx`。
- 风格与 `RowDetailDrawer` 同款：mask + fixed right-0 + Escape 关闭 + body overflow 锁定 + 响应式宽度。
- 接口：
  ```ts
  interface RowDetailDrawerBondProps {
    fund: FundListItem | null;       // null = 关闭
    onClose: () => void;
  }
  ```
- 内部：`fund` 变化时按 `fundApi.getDetail(code)` 拉详情（**注意用 fundApi 而非 stockApi**，因为债基路由是 `/api/funds/*`）；骨架屏 + 失败兜底。

#### 表 1：持仓分析

包含三块：

**A. 券种配置饼图（手写 SVG）**
- 三档：`rate_bond_pct` / `credit_bond_pct` / `convertible_pct`
- 第四档：`other = 100 - (rate + credit + convertible)`（兜底，可能 > 0 表示现金/同业存单等）
- 圆环图：外径 r=60，内径 r=40；4 段按比例拼接；图例右侧展示"利率/信用/可转债/其他" + 百分比 + 颜色块
- 配色（globals.css 已有的语义色）：
  - 利率债 → `var(--color-info)` 深蓝灰（低风险）
  - 信用债 → `var(--color-accent)` 暖橘红（中风险）
  - 可转债 → `var(--color-up)` 绿色（权益属性）
  - 其他 → `var(--color-rule-strong)` 灰（中性）

**B. 持仓集中度**
- `top5_concentration` 数字 + 横向进度条（0-50% 量程，>50% 染色）
- 文案：`前 5 大债券占比：{pct}%`
- 进度条颜色：≤30% 绿（up），30-50% 黄（star），>50% 红（down）

**C. 前五大债券明细**
- 解析 `top5_bonds` 字符串（格式：`21民生银行永续债01(6.8%); 25进出01(2.6%); ...`）→ 数组 `[{name, pct}, ...]`
- 表格：名称 + 占比（按 pct desc）
- 缺失字段显示 `-`

#### 表 2：费率明细

- 与股票抽屉完全一致：申购 / 4 档赎回 / 3 项年费 / 年费合计（沿用 RowDetailDrawer.tsx:13-23 FEE_ROWS；建议抽到 `lib/feeRows.ts` 复用）。

### REQ-3 债基 page 集成

- `apps/fund-select/src/app/bond/page.tsx`：
  - 新增 `const [detailFund, setDetailFund] = useState<FundListItem | null>(null)`
  - `<FundTable ... onRowClick={setDetailFund} />`（注意 FundTable 已支持 onRowClick）
  - 末尾渲染 `<RowDetailDrawerBond fund={detailFund} onClose={() => setDetailFund(null)} />`

### REQ-4 测试

- 前端无单测框架；沿用 tsc + build + 手动截图。
- 后端不动（数据已就绪），回归测试预期 171 passed。

## Acceptance Criteria

| ID | 标准 | 映射 REQ |
|---|---|---|
| AC-1 | 债基 tab FundTable 主表列数 14 → 13（移除年费列）；不再显示"年费"列 | REQ-1 |
| AC-2 | 债基行 `<tr>` 有 `cursor-pointer` + onClick（沿用 stock 抽屉 onRowClick 机制） | REQ-3 |
| AC-3 | 点击对比按钮不触发行 click（stopPropagation 沿用） | REQ-3 |
| AC-4 | 点击任意一行 → 右侧抽屉滑出；mask 半透明黑；Escape 关闭；body overflow 锁定 | REQ-2 |
| AC-5 | 抽屉头部显示基金代码 + 名称 + 类型 | REQ-2 |
| AC-6 | 持仓表 1-A：券种饼图（圆环）4 段渲染：利率/信用/可转债/其他；缺失段隐藏 | REQ-2 |
| AC-7 | 持仓表 1-B：前 5 大集中度数字 + 进度条；>50% 染色红 | REQ-2 |
| AC-8 | 持仓表 1-C：前五大债券明细表，每行名称 + 占比；缺失字段 `-` | REQ-2 |
| AC-9 | 表 2：费率明细 8 项 + 年费合计；与股票抽屉完全一致 | REQ-2 |
| AC-10 | 关闭抽屉回到列表，列表状态保留（筛选/排序不动） | REQ-2, REQ-3 |
| AC-11 | 移动端（xs < 640px）：抽屉全屏 95vw；桌面端（xl ≥ 1280px）：900px | REQ-2 |
| AC-12 | 股票 tab FundTable **完全不动**（不引入 RowDetailDrawerBond、不改 onRowClick） | REQ-1, REQ-3 |
| AC-13 | 后端 pytest 171 passed（不动后端） | REQ-4 |
| AC-14 | 前端 `pnpm tsc --noEmit` 通过 | REQ-4 |
| AC-15 | 截图：列表 13 列（无年费列）、抽屉展开（饼图 + 集中度 + 前五大 + 费率）、移动端全屏 | REQ-4 |

## Non-Goals

- ❌ 不抽 `Drawer` 基础组件；新建独立组件 RowDetailDrawerBond。
- ❌ 不改债基 / 股票 DTO（数据已足够）。
- ❌ 不在抽屉里展示业绩 / 经理 / 基础信息（用户决策"精简 2 张表"）。
- ❌ 不做债基同类排名（无 ETL，刷新流程扩展是另一任务）。
- ❌ 不做新持仓 ETL（杠杆率 / 久期 / 机构占比等待扩展）。
- ❌ 不引入图表库（饼图手写 SVG）。

## Technical Notes

- **数据来源**：`fundApi.getDetail(code)` 返回 FundDetail 含 `holdings: FundHoldings | null`；其他字段保留兼容。
- **圆环图 SVG**：4 段按比例拼接，stroke-dasharray + stroke-dashoffset 实现；外径 60 + 内径 40 = 20 像素环宽；总周长 = 2π × (60+40)/2 ≈ 314（用 viewBox 自动缩放）。
- **top5_bonds 解析**：`top5_bonds.split('; ').map(s => { const m = s.match(/^(.+?)\(([\d.]+)%\)$/); return m ? {name: m[1], pct: Number(m[2])} : null; }).filter(Boolean)`
- **缺失兜底**：holdings = null 时持仓表 1 显示"暂无持仓数据"占位。
- **样式参考**：`RowDetailDrawer.tsx:48-82` mask + fixed + 响应式宽度代码可复制；FEE_ROWS 数组可直接复制（或抽到 lib/feeRows.ts 复用）。
- **feeRows 复用建议**：把 FEE_ROWS 抽到 `apps/fund-select/src/lib/feeRows.ts`，RowDetailDrawer 和 RowDetailDrawerBond 都 import。

## Risks / Rollback

- **风险 1**：饼图 SVG 拼接算法出错 → 准备单测覆盖（极简：测总占比 = 100%）；fallback 用 stacked bar。
- **风险 2**：top5_bonds 解析失败（格式异常）→ try/catch + 显示原始字符串。
- **风险 3**：债基 page FundTable "年费"列移除后某些债基筛选用户的视觉习惯改变 → 列表更宽可缓解；如反馈强烈可回滚。
- **风险 4**：与 RowDetailDrawer 视觉差异 → 风格已对齐（同 mask + Escape + 响应式宽度）。
- **回滚步骤**：
  1. 删除 `RowDetailDrawerBond.tsx`。
  2. bond/page.tsx 移除 `setDetailFund` state 与 RowDetailDrawerBond 渲染。
  3. FundTable 恢复"年费"列 th 和 td。
