# Implement：债基 tab 行点击详情抽屉

## 实施清单（按依赖顺序）

### Phase A：抽取 FEE_ROWS 到 lib

- [ ] **A1**. 新建 `apps/fund-select/src/lib/feeRows.ts`，导出 `FEE_ROWS` 数组（与 RowDetailDrawer.tsx:13-23 内容完全一致）。
- [ ] **A2**. `RowDetailDrawer.tsx` 删本地 FEE_ROWS，改为 `import { FEE_ROWS } from '@/lib/feeRows'`。

### Phase B：FundTable 移除"年费"列

- [ ] **B1**. `apps/fund-select/src/components/FundTable.tsx` 删 th `<SortableHeader label="年费" ... />`。
- [ ] **B2**. 删 td `<td>{fmt(fund.fee_annual, 2, '%')}</td>`。
- [ ] **B3**. 验证 FundTable 不再引用 `fund.fee_annual`。

### Phase C：新建 RowDetailDrawerBond

- [ ] **C1**. 创建 `apps/fund-select/src/components/RowDetailDrawerBond.tsx`：
  - 与 RowDetailDrawer 同款 mask + fixed right-0 + Escape + body overflow + 响应式宽度（复制自 RowDetailDrawer.tsx:48-82）。
  - 接口：`{ fund: FundListItem | null; onClose: () => void }`。
- [ ] **C2**. 内部 state + useEffect 拉详情（**用 fundApi 不是 stockApi**）：
  ```ts
  useEffect(() => {
    if (!fund) { setDetail(null); return; }
    let cancelled = false;
    fundApi.getDetail(fund.code)
      .then(d => { if (!cancelled) setDetail(d); })
      .catch(() => { if (!cancelled) setDetail(null); });
    return () => { cancelled = true; };
  }, [fund?.code]);
  ```
- [ ] **C3**. 头部：代码 + 名称 + 类型 + 关闭按钮（沿用 RowDetailDrawer 头部样式）。
- [ ] **C4**. 持仓表 1 标题："持仓分析（{report_date} 报告期）"，缺失 holdings 显示"暂无持仓数据"。
- [ ] **C5**. 持仓表 1-A：DonutChart 子组件
  - props: `{ rate: number | null; credit: number | null; convertible: number | null }`
  - 手写 SVG 圆环，4 段拼接（其他 = 100 - 已知之和）
  - 缺失段（pct = null）按 0 处理；总占比 < 0.5% 的段不渲染
  - 图例右侧展示名称 + 百分比 + 颜色块
- [ ] **C6**. 持仓表 1-B：持仓集中度进度条
  - 数字 `前 5 大债券占比：{pct}%`
  - 进度条 0-50% 量程
  - 颜色：≤30% bg-up；30-50% bg-star；>50% bg-down；缺失 bg-paper-deep
- [ ] **C7**. 持仓表 1-C：前五大债券明细表
  - 用 `parseTop5Bonds(top5_bonds)` 解析
  - 列：名称 + 占比（按 pct desc，已按 desc 排序无需再排）
  - 缺失 holdings 整段隐藏
- [ ] **C8**. 表 2：费率明细（复用 FEE_ROWS）
  - 沿用 RowDetailDrawer FEE_ROWS 渲染方式
  - 末行"年费合计"，缺失字段 "-"

### Phase D：债基 page 集成

- [ ] **D1**. `apps/fund-select/src/app/bond/page.tsx`：
  - `import { useState }` 已有
  - `import { RowDetailDrawerBond }` 新增
  - 新增 `const [detailFund, setDetailFund] = useState<FundListItem | null>(null)`
  - `<FundTable ... onRowClick={setDetailFund} />`
  - 在 CompareDrawer 后追加 `<RowDetailDrawerBond fund={detailFund} onClose={() => setDetailFund(null)} />`

### Phase E：验证

- [ ] **E1**. 后端（回归）：`cd backend/fund-select && python -m pytest tests/ -v` 期望 171 passed
- [ ] **E2**. 前端：`cd apps/fund-select && pnpm tsc --noEmit` 通过
- [ ] **E3**. 启动 dev server，访问 `/funds`：
  - 列表 13 列（无年费列）
  - 行 hover cursor-pointer
  - 点击对比按钮 → 只切换对比、不触发行 click
  - 点其他位置 → 右侧抽屉滑出
  - 持仓表 1：圆环图 4 段渲染（如 217022 是 2.6/14.1/0/83.3）
  - 持仓表 1-B：集中度 16.7% + 进度条
  - 持仓表 1-C：前五大债券 5 行明细
  - 费率表 2：8 项 + 年费合计
  - Escape / mask / 关闭按钮都能关闭
  - 关闭后列表状态保留
- [ ] **E4**. 访问 `/funds/stock`：列表 12 列（不变），抽屉不变
- [ ] **E5**. 截图：列表 13 列、抽屉展开（饼图 + 集中度 + 前五大 + 费率）、移动端（xs 375px）抽屉全屏

## 关键文件清单

| 文件 | 改动类型 |
|---|---|
| `apps/fund-select/src/lib/feeRows.ts` | **新建** A1 |
| `apps/fund-select/src/components/RowDetailDrawer.tsx` | A2：FEE_ROWS import 改 |
| `apps/fund-select/src/components/RowDetailDrawerBond.tsx` | **新建** C1-C8 |
| `apps/fund-select/src/components/FundTable.tsx` | B1-B3：删年费列 |
| `apps/fund-select/src/app/bond/page.tsx` | D1：state + 渲染 |
| `apps/fund-select/src/app/stock/page.tsx` | 0 改动（验证不动） |

## 回滚点

- Phase A 失败可单独回滚：FEE_ROWS 留在 RowDetailDrawer 内联（同时保留 lib/feeRows.ts 不引用即可）。
- Phase B 失败可单独回滚：FundTable 恢复"年费"列 th + td。
- Phase C 失败可单独回滚：RowDetailDrawerBond 不被引用；bond page 不引入。
- Phase D 失败可单独回滚：bond page 移除 setDetailFund 与 RowDetailDrawerBond。

## 风险点（先验）

1. **饼图 SVG 渲染**：用 `viewBox="0 0 120 120"` + `r=50` 内置圆周长公式；如渲染错位可参考 Phase E 截图验证。
2. **top5_bonds 格式**：实际格式 `21民生银行永续债01(6.8%); ...`；正则 `^(.+?)\(([\d.]+)%\)$` 兼容。
3. **响应式宽度**：与股票抽屉同款，复用逻辑。
4. **FundTable 列宽**：移除 1 列后，对比列右侧留空，视觉更宽松。
