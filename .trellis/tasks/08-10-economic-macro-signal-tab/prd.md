# economic 页面新增宏观经济信号卡片面板 Tab

> 修订 v3(2026-08-10): 按 demo v2 终稿,移除 score / 维度级 data_date,保留 skill 的定性结论作为卡头主信号,每个指标带各自的更新时间。6 大主题仅作分组容器。

## Goal

在 `apps/economic` 现有 7 个 Tab 之外,新增第 8 个 Tab「宏观信号」,以 6 个分组卡片展示当月宏观判断结果。每张卡片:**分组名(小字标识)+ skill 定性结论(大号加粗主信号)+ 该分组下所有指标明细(每个指标各带更新时间)**。提供月份切换 + 发布日历。组件只负责展示,数据通过 Props 由父组件注入(本期 mock,后端接口由后续 agent 接入)。

## Background

数据来源(`F:\personal-projects\macro-fin-skill\skills`)的 6 个子 skill 各产出一份 `macro_signal.json`,字段含 `score` / `conclusion` / `details`。本任务**只展示 conclusion 和 details 中各指标的原始数值**,不展示 score。每个指标的更新时间在 skill 现有输出里没有粒度到指标级,本期 mock 自造,后续 agent 接口时由后端按指标级返回。

## Requirements

### 功能需求

- **R1 新 Tab「宏观信号」**: 加入 `apps/economic` 页面 Tab 列表(放在股指之后)。Tab 切换时与其他 Tab 一样仅 hidden 控制显隐。
- **R2 月份切换器**: 「上一月 / 下一月 / 月份下拉」三种入口,粒度仅月度,最近 12 个月范围。**切换月份触发数据重新请求**(本期走 mock 异步函数,后续 agent 替换为接口 fetch),加载期间显示 loading 占位。
- **R3 6 张分组卡片(网格布局)**: 每张卡固定渲染结构:
  - **卡头第一行(小字标识)**: 圆点(维度身份色)+ 分组名(货币政策 / 信用扩张 / 经济运行 / 通胀环境 / 外部压力 / 市场情绪)+ 右侧"X 项指标"
  - **卡头第二行(主信号)**: skill 定性结论文字(20px 加粗白色),如「温和」「信用扩张」「适度宽松」「外部中性」「偏热」等
  - **指标列表**: 每行 = 指标中文 label + 数值(单位 + 小数位)+ 该指标的更新时间(`YYYY-MM-DD · N 天前`)
  - 整组数据缺失(无 indicators)时:卡头第二行显示「数据缺失」(灰色加粗),列表区显示「本月数据缺失」
  - 单个指标值 null/updated_at null:显示 `—` + 「本月无数据」
  - 指标更新时间距所选月初 35 天以上:更新时间用黄字 + 「数据偏旧」后缀
- **R4 发布日历**: 卡片网格下方展示当月日历(6×7,周一起始),根据硬编码发布规则(CPI/PPI 每月10日、固投/工业增加值/社零 13日、MLF 15日、LPR 20日、用电量 20日、铁路货运 7日、汇率/DR007/风险偏好 每工作日)在每个日期画对应维度的色点。点击日期弹出 popover 显示当天发布的指标列表。今日蓝边框高亮,未来日期灰显。
- **R5 mock 数据**: 3 个月快照(2026-03 / 2026-04 / 2026-05),按 `Record<month, Record<DimensionKey, MacroSignalGroup>>` 结构组织。本月数据从 skill JSON 直接复制结论 + 指标值,所有指标配上 updated_at。另两个月数值 ±10% 扰动 + 更新日期前移一月。`loadMockSnapshot(month)` 异步函数 + 300ms setTimeout 模拟网络延迟。
- **R6 Props 契约(对外接口)**: 容器组件 `MacroSignalTab` 接收:
  - `loadSnapshot: (month: string) => Promise<MacroSignalSnapshot | null>` — 月份数据加载函数
  - `availableMonths: string[]` — 可切换月份列表(YYYY-MM)
  - `initialMonth?: string`
  内部 `useState(selectedMonth)` + `useEffect` 监听变化触发 loadSnapshot,管理 loading/error/snapshot 三态。

### 接口契约(后续 agent 实现后端时按此返回)

请求: `GET /api/macro/signal?month=2026-05`(具体路径后端自定)

响应 `MacroSignalSnapshot` 形状:

```typescript
{
  month: '2026-05',
  generated_at: '2026-05-22T07:28:47Z',
  groups: {
    monetary_policy: {
      conclusion: '适度宽松',     // skill 的定性结论,可为 null
      indicators: [
        { key: 'dr007',  value: 1.328, updated_at: '2026-05-21' },
        { key: 'lpr_1y', value: 3.00,  updated_at: '2026-05-20' },
        // ...
      ]
    },
    inflation: {
      conclusion: '温和',
      indicators: [
        { key: 'cpi_yoy', value: 1.2, updated_at: '2026-05-10' },
        // ...
      ]
    },
    // ... 其他 4 个分组
  }
}
```

**关键点**:
- 后端**按分组返回 conclusion + indicators**,不是返回 score
- 每个 indicator **必须带自己的 updated_at**(粒度到指标级,不是分组级)
- 6 个分组的 key 固定:`monetary_policy` / `money_supply` / `entity_economy` / `inflation` / `exchange_rate` / `risk_appetite`
- value 为 null 表示该指标本月无数据;整组 indicators 为空数组表示整组缺失

### 非功能需求

- **N1 视觉一致性**: 沿用 economic 现有主题(bg-black 主背景、bg-gray-900 卡片背景、border-gray-800 边框、text-gray-400 副文本、Tailwind v4)。
- **N2 不引入新依赖**: 不引日历库(date-fns/dayjs)、不引 UI 库。
- **N3 不污染现有数据流**: 新 Tab 不依赖 `useFullEconomicData`,数据走自己的 Props 通道。
- **N4 不写后端**: 本期纯前端 + mock。

## Out of Scope

- ❌ score 数字(0-100)
- ❌ 评分色阶(紫绿蓝橙红)
- ❌ 综合指数(a-share 综合 / 债市综合)
- ❌ 周切换 / 日切换 — 仅月度
- ❌ 后端接口开发 — 留给后续 agent
- ❌ 数据自动刷新按钮 — 数据由父级注入,本期静态 mock
- ❌ 维度级 data_date 字段(指标级 updated_at 已覆盖该语义)

## Acceptance Criteria

- [ ] AC1 点击「宏观信号」Tab 能切换,不破坏现有 7 个 Tab 的状态
- [ ] AC2 默认显示当月(最新 mock 月)的 6 张分组卡
- [ ] AC3 月份切换器能在 3 个月之间切换,**切换时 loading 占位可见**,卡片 conclusion + 指标数值都变
- [ ] AC4 每张分组卡渲染:卡头第一行(圆点+分组名+X 项指标)、第二行(20px 加粗白色 conclusion)、指标列表(label + value + updated_at)
- [ ] AC5 6 个 conclusion 在切月时正确变化(如通胀环境 5 月「温和」→ 4 月「低通胀偏冷」)
- [ ] AC6 单个指标 value=null 显示「—」;整组 indicators=[] 卡头显示「数据缺失」、列表区显示「本月数据缺失」
- [ ] AC7 指标 updated_at 距所选月初 35 天以上,时间用黄字 + 「数据偏旧」
- [ ] AC8 日历视图显示当月,色点按发布规则(CPI 10日、固投 13日、MLF 15日、LPR 20日 等),点击弹出 popover,今日蓝边框,未来日期灰显
- [ ] AC9 `MacroSignalTab` 容器组件 Props 形状 = `loadSnapshot + availableMonths + initialMonth?`
- [ ] AC10 `pnpm lint` + `pnpm build` 在 apps/economic 通过

## Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| skill 的 details 字段未来扩展(如实体加新指标) | indicators 用开放式数组,前端查 INDICATOR_LABELS 表,fallback 到原 key |
| 后端 agent 按接口契约返回时把 score 也带上 | 前端类型定义不含 score 字段,JSON 多余字段自动忽略 |
| 不同月份 mock 数据手写易错 | helper `shiftSnapshot(snapshot, monthOverride, factor)` 自动生成历史月份 |
| TabType 在 lib/types/economic.ts 已含 8 个值但 /lib/modules/economic/types.ts 是旧版(只 2 个) | 沿用 page.tsx 实际 import 的 lib/types/economic.ts,只在其 TabType union 加 'macro-signal' |

## Notes

- 数据契约主要参考: `F:\personal-projects\macro-fin-skill\skills\*-skill\macro_signal.json` 的 `conclusion` 字段 + `details` 字段(各指标数值);指标级 updated_at 由后端 agent 后续按发布规则填入
- 发布时间规则参考各 skill 的 SKILL.md「数据频率 / 发布时间」表
- 容器组件命名 `MacroSignalTab`,分组卡组件命名 `GroupCard`,与现有 `StockIndexTab` / `RatesTab` 等保持一致
