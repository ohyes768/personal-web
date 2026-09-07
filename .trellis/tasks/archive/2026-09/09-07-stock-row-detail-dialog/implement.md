# Implement：股票基金行点击详情弹框

## 实施清单（按依赖顺序）

### Phase A：FundTable 列调整 + 行交互

- [ ] **A1**. 删除 `apps/fund-select/src/components/FundTable.tsx`：
  - `RANK_TIPS` 常量
  - `rankColor()` 函数（保留作抽屉复用——可移动到 `lib/rankColor.ts` 或抽屉内复用代码）
  - `<RankChip>` 组件（保留作抽屉复用——同上）
  - `showRankColumns` 相关 th/td JSX
  - "年费"列 th（`<SortableHeader label="年费"...>`）和 td
  - `showRankColumns?: boolean` prop（如债基 page 没引用则彻底删）
- [ ] **A2**. `FundTableProps` 新增 `onRowClick?: (fund: FundListItem) => void`。
- [ ] **A3**. 行 `<tr>` 加：
  ```tsx
  onClick={onRowClick ? () => onRowClick(fund) : undefined}
  className={`... cursor-pointer ${onRowClick ? 'cursor-pointer' : ''}`}
  ```
- [ ] **A4**. 对比按钮 onClick 加 `e.stopPropagation()`：
  ```tsx
  onClick={(e) => { e.stopPropagation(); onToggleCompare(fund); }}
  ```
- [ ] **A5**. 删除表格下方"排名口径"脚注（`showRankColumns && ...` 块）。

### Phase B：新建 RowDetailDrawer 组件

- [ ] **B1**. 创建 `apps/fund-select/src/components/RowDetailDrawer.tsx`：
  - 基础结构与 `CompareDrawer.tsx:48-82` 对齐（mask + fixed right-0 + Escape + body overflow + 响应式宽度）。
  - 接口：`{ fund: FundListItem | null; onClose: () => void }`。
- [ ] **B2**. 内部 state：
  - `const [detail, setDetail] = useState<FundDetail | null>(null)`
  - `const [loading, setLoading] = useState(false)`
- [ ] **B3**. useEffect 监听 `fund?.code` 调 `stockApi.getDetail(code)`，清理用 cancelled 标志。
- [ ] **B4**. 头部：`<h2>{fund.code} {fund.name}</h2>` + 关闭按钮。
- [ ] **B5**. 三张表骨架屏（loading=true 时）：
  ```tsx
  <div className="h-4 bg-paper-deep rounded animate-pulse" />
  ```
- [ ] **B6**. 表 1：4 周期排名（按 RANK_PERIODS 顺序）：
  ```ts
  const PERIODS = [
    { kind: '年度业绩', period: '今年以来', label: '今年以来' },
    { kind: '阶段业绩', period: '近1年',    label: '近 1 年' },
    { kind: '阶段业绩', period: '近3年',    label: '近 3 年' },
    { kind: '阶段业绩', period: '近5年',    label: '近 5 年' },
  ] as const;
  ```
  - 每行：周期名 + 收益（红绿色）+ 百分位 chip + 原始排名（peer_rank 字符串）
  - 缺失字段显示 `-`
- [ ] **B7**. 表 2：历年年度业绩（完整展示）：
  ```ts
  const annuals = (detail?.achievement_ranks ?? [])
    .filter(r => r.period_kind === '年度业绩')
    .sort((a, b) => {
      if (a.period === '成立以来') return 1;
      if (b.period === '成立以来') return -1;
      if (a.period === '今年以来') return -1;
      if (b.period === '今年以来') return 1;
      return Number(b.period) - Number(a.period);
    });
  ```
  - 同样：年份 + 收益（红绿色）+ 百分位 chip + 原始排名
  - 注意 `_parse_peer_rank` 在前端没有；raw `peer_rank` 字符串直接展示即可（如 `"1014/5616"`）
- [ ] **B8**. 表 3：费率明细（按 feeDetailDimensions 顺序）：
  ```ts
  const FEE_ROWS = [
    { key: 'fee_buy_small',    label: '申购费(小额档)' },
    { key: 'fee_redeem_lt7d',   label: '赎回 <7天' },
    { key: 'fee_redeem_7d_1y',  label: '赎回 7天~1年' },
    { key: 'fee_redeem_ge1y',   label: '赎回 ≥1年' },
    { key: 'fee_redeem_ge7d',   label: '赎回 ≥7天' },
    { key: 'fee_mgmt',          label: '管理费', suffix: '/年' },
    { key: 'fee_custody',       label: '托管费', suffix: '/年' },
    { key: 'fee_service',       label: '销售服务费', suffix: '/年' },
  ];
  ```
  - 末行 `年费合计 = mgmt + custody + service`（任一缺失显示 `-`）
  - 费率数字用 `2 位小数 + '%'`
- [ ] **B9**. `rankColor()` 与 `<RankChip>` 组件如 Phase A 移走，需重新 import 到 RowDetailDrawer 内部（或抽到 `lib/rankColor.ts`）。

### Phase C：stock page 集成

- [ ] **C1**. `apps/fund-select/src/app/stock/page.tsx`：
  - 新增 `const [detailFund, setDetailFund] = useState<FundListItem | null>(null)`
  - `<FundTable ... onRowClick={setDetailFund} showRiskColumns />`（移除 showRankColumns）
  - 在 page 末尾（CompareDrawer 旁边）渲染 `<RowDetailDrawer fund={detailFund} onClose={() => setDetailFund(null)} />`

### Phase D：验证

- [ ] **D1**. 后端（回归）：`cd backend/fund-select && python -m pytest tests/ -v` 期望 171 passed
- [ ] **D2**. 前端：`cd apps/fund-select && pnpm tsc --noEmit` 通过
- [ ] **D3**. 前端：`pnpm build`，EPERM 既有可忽略
- [ ] **D4**. 启动 dev server（后端 8095 + 前端 3005），访问 `/funds/stock`：
  - 列表列数回退到 12 列（不含对比）
  - 行 hover cursor-pointer；点击对比按钮 → 只切换对比状态、不触发抽屉
  - 点击其他位置 → 右侧抽屉滑出
  - 抽屉头部代码 + 名称正确
  - 4 周期排名表渲染（如 005827 已知有数据）
  - 历年年度业绩完整展示（>10 行）
  - 费率明细 8 项 + 年费合计
  - Escape / mask / 关闭按钮都能关闭
  - 列表筛选 / 排序状态保留
- [ ] **D5**. 截图：
  - 列表 13 列布局（无排名列、无年费列）
  - 抽屉展开（3 张表都填好数据）
  - 移动端（DevTools 切到 xs 375px）抽屉全屏
- [ ] **D6**. 访问 `/funds`（债基）：确认列表 14 列布局（含利率债），无行点击响应（hover 无 cursor-pointer 视觉反馈）

## 关键文件清单

| 文件 | 改动类型 |
|---|---|
| `apps/fund-select/src/components/FundTable.tsx` | A1-A5：删列、加行交互 |
| `apps/fund-select/src/components/RowDetailDrawer.tsx` | **新建** B1-B9 |
| `apps/fund-select/src/app/stock/page.tsx` | C1：state + 传参 |
| `apps/fund-select/src/app/bond/page.tsx` | 0 改动（验证不动） |
| `apps/fund-select/src/app/globals.css` | 0 改动（保留 --color-rank-*） |
| `backend/fund-select/...` | 0 改动（回归保护） |

## 回滚点

- Phase A 失败可单独回滚：保留 4 排名列 + 1 年费列，删除 onRowClick prop 与 stopPropagation。
- Phase B 失败可单独回滚：RowDetailDrawer 不被引用、stock page 不引入。
- Phase C 失败可单独回滚：stock page 移除 setDetailFund 与 RowDetailDrawer。

## 风险点（先验）

1. **数据缺失**：507918 / 968157 等老基金无雪球年度业绩 → 表 2 自然为空或仅"成立以来"一行（兜底）。
2. **peer_rank 解析缺失**：详情接口已用 `_parse_peer_rank` 解析过，但当前列表 DTO 里只有 `rank_ytd/_1y/_3y/_5y` 4 个 pct dict；表 2（历年）需要原始 `"1014/5616"` 字符串 → **用 `detail.achievement_ranks[i].peer_rank`（string | null）直接展示**，无需重新解析。
3. **列宽风险**：移除 4 排名列 + 1 年费列后，"对比"列右侧会留空 → 不影响功能、视觉更宽松。
4. **mask 与 CompareDrawer 同时打开**：业务上不发生（先关 CompareDrawer 才能点行），如发生按 z-index 50 同级，后开者覆盖。
