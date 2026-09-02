# 股票基金筛选 tab

## Goal

在 apps/fund-select 前端新建股票基金筛选 tab，作为现有债基 tab 的并列入口。后端复用 backend/fund-select 的 akshare 采集链路，新增股票型 + 偏股混合基金的筛选项与展示列。

**两阶段交付**：第一阶段把"基础筛选 + 基础业绩/回撤展示"跑通；第二阶段补齐业绩对比基准、夏普、IR、选股/择时/Alpha IR 等需额外算的指标。

## Background & 调研结论

已在 tmp/ 下做了两轮 demo 跑通：

| 数据项 | 接口 | 状态 |
|---|---|---|
| 基金代码/名称/类型/规模/经理/公司/费率/业绩公式 | `fund_individual_basic_info_xq` | ✅ 已有 |
| 单位净值序列 | `fund_open_fund_info_em` (单位净值走势) | ✅ 已有 |
| 1y/3y/5y 收益 + 1y/3y 回撤（窗口算法） | `compute_performance` | ✅ 已有 |
| 同类排名 + 区间收益 + 区间最大回撒（按周期） | `fund_individual_achievement_xq` | ✅ 新增可用 |
| 累计收益率走势 / 同类排名走势 | `fund_open_fund_info_em` (其他 indicator) | ✅ 新增可用 |
| **业绩比较基准代码（多个）** | ❌ akshare 不给；baostock 没基金 API | 第一阶段降级 |
| 夏普比率 | ❌ akshare 无；empyrical Python 3.13 装不上 | 自算（待选无风险利率）|
| 信息比率 IR | ❌ 同上 + 需基准日收益 | 自算 |
| 选股 α / 择时 γ / 选股 α IR | ❌ 同上 + 需基准日收益 | 自算 T-M 回归 |

## 范围

### 第一阶段（本次 sprint 实施）

**筛选维度（默认阈值）**：

| 维度 key | 默认阈值 | 备注 |
|---|---|---|
| `min_age` | 3 | 成立年限 ≥ 3 年（用户原话）|
| `min_size_yi` | 5 | 规模 ≥ 5 亿元 |
| `min_mgr_exp` | 5 | 经理总从业年限 > 5 年（即 ≥ 5；保留 1 位小数）|
| `max_dd_3y` | 20 | 近 3 年最大回撤 < 20% |

**表格展示列**：

- 基础：代码 / 名称 / 基金类型 / 规模（亿）/ 经理 / 公司
- 费率：管理 / 托管 / 销售服务 / 年度总费用（已有 fund_fees）
- 业绩：1y / 3y / 5y 收益率（窗口）
- 回撤：1y / 3y 净值窗口最大回撤
- 业绩排名：成立以来 / 1y / 3y / 5y 同类排名（来自 achievement_xq，可选）

**名单 & 采集**：

- demo 先用 30 只代表性股票型 / 偏股混合基金，手工给名单（仿 `config/funds.yaml` 模式）
- 后续扩到全市场股票型 + 偏股混合（v2 选题）

**采集流程**：

- 复用 `refresh_service.snapshot_fund` 主流程
- 新增 achievement_xq fetcher，仅股票型 + 偏股混合跑（不是所有基金都有标准 achievement_xq 返回）
- 入库 FundPerformance + 新增 FundAchievementRank 表

**tab 切换**：

- `/funds` 路由下加 tab 控件：债基 | 股票
- tab 切换写入 URL（`?tab=stock`），与筛选参数并存

### 第二阶段（待实施，本 PRD 不开 plan）

**新增指标**：

- 业绩比较基准（TRI）的同期收益 + 超额收益
- 信息比率 IR = `(R_p - R_b).mean() / std * √252`
- 夏普比率 = `(R_p - R_f).mean() / std * √252`
- 选股能力 α（T-M 截距，年化）
- 择时能力 γ（T-M 二次项系数）
- 选股 α IR = `α / σ_residual * √252`

**实施前置条件**：

- 完成"指数代码 yaml 映射"（~30 个常见指数：沪深 300/500/1000、上证 50、中证 800、白酒、医药、港股通综合、中债总指数等）
- 确认无风险利率数据源（选 `ak.bond_zh_us_rate` 中国国债 / LPR / 常数兜底之一）
- 完成 `src/data/benchmark_fetcher.py`（解析公式 → 查 yaml → 拉指数日线 → 加权合成）
- 完成 `src/services/risk_service.py`（Sharpe / IR / T-M / α-IR）

不在本 PR 范围。

## Constraints

1. 后端只新增 fetcher 和计算服务；不动现有债基 tab 的任何逻辑。
2. 复用现有 fastapi / sqlalchemy / akshare / apscheduler 技术栈，不引入新外部数据源（akshare 已够）。
3. 第一阶段不实现业绩对比基准（避免引入指数日线 + 公式解析的不确定性）。
4. 第二阶段写明为后续单独 task，本 PRD 不开 plan / design / implement。

## Acceptance Criteria

### 第一阶段

- [ ] **独立路由** `/funds/stock`（前端 `app/stock/page.tsx`）和现有 `/funds` 平列；两页面共享 `FundsHeader` 组件，header 上的「债基 | 股票」链接互相跳转。
- [ ] 进入股票页，应用默认筛选条件（成立年限 ≥3 / 规模 ≥5亿 / 经理 ≥5 年 / 近 3 年回撤 <20%）；通过 `useFilters` 接受 initial override 实现（参见 design.md）。
- [ ] 股票页表格展示列与债基页一致：代码 / 名称 / 类型 / 规模 / 经理 / 公司 / 1y / 3y / 5y 收益 / 1y / 3y 回撤；空值显示 "—"。
- [ ] 至少 30 只代表性股票型 + QDII 基金入库；后台跑 refresh pipeline 一次跑通，无 schema 错误。
- [ ] 表格列名跟债基页一致；排序按钮工作；导出 CSV 工作。
- [ ] 顶部筛选 chip 区能正常点击移除，回到默认（用现有 `cleared=1` 逻辑）。
- [ ] `pnpm exec tsc --noEmit` 0 错；`pnpm build` 类型检查 + 静态生成都过。
- [ ] 后端 `pytest tests/ -v` 全过，新增单测覆盖 achievement_xq fetcher 与新过滤器。
- [ ] 不引入新的 .env 变量；不引入新外部网络依赖（akshare 已有覆盖）。
- [ ] 复用现有 `FilterPanel` / `FilterSheet` / `FilterChipBar` / `FundTable` / `ExportCsvButton` / `RefreshStatusPopover` / `CompareDrawer` / `CompareFloatingBar` 组件，不复制粘贴实现。

### 第二阶段（不在本次验收）

- 业绩基准 / IR / 夏普 / 选股 / 择时 / α-IR — 单独后续 PRD 与 implement。

## Decisions（已拍）

1. **tab 基金类型范围** → `股票型-*` + QDII（用户原意；混合型偏股不收）
2. **基金名单来源** → 手工 yaml，30 只代表性基金（仿 `funds.yaml` 模式）
3. **业绩基准实现路径** → **不展示**（第二阶段先走通再说）
4. **业绩对比窗口** → 随决策 3 作废（不展示即无窗口问题）
5. **夏普无风险利率数据源** → 留第二阶段拍（本次不实现）
6. **tab URL 策略** → 独立路由 `/funds/stock`
7. **achievement_xq "周期最大回撒"入库** → 不入库（窗口回撤已经覆盖，混用会引概念混淆）

> 决策 3 选定 C 后，第二阶段依赖业绩基准的指标（IR / 选股 α / 择时 γ / 选股 α IR）全部后置；夏普比率独立可算，但用户原话"放第二阶段"，所以同样后置。第二阶段 PRD 单独开。

## Acceptance Criteria

### 第一阶段

- [ ] 新增路由 `/funds/stock`，复用现有 `/funds` 顶部组件与样式体系（不共享筛选 state，独立的 useFilters 实例）。
- [ ] 应用默认筛选条件（成立年限 ≥3 / 规模 ≥5亿 / 经理 ≥5 年 / 近 3 年回撤 <20%）。
- [ ] 表格列：代码 / 名称 / 类型 / 规模 / 经理 / 公司 / 1y / 3y / 5y 收益 / 1y / 3y 回撤 + 同类排名（成立以来 / 1y / 3y / 5y 可选）。
- [ ] 至少 30 只代表性基金入库；后台跑 refresh pipeline 一次跑通，无 schema 错误。
- [ ] achievement_xq fetcher 单独跑（不上传到多余列，避免数据库冗余）；fetch 结果入库到 `fund_achievement_rank` 表。
- [ ] 不引入业绩基准 / IR / 夏普 / 选股 / 择时 字段的采集或展示（避免第二阶段 schema 冲突）。
- [ ] `pnpm exec tsc --noEmit` 0 错；`pnpm build` 类型检查 + 静态生成都过。
- [ ] `cd backend/fund-select && uv run pytest tests/ -v` 全过；新增单测覆盖 achievement_xq fetcher。
- [ ] 不引入新的 .env 变量；不引入新外部网络依赖（akshare 已有覆盖）。

### 第二阶段（不在本次验收）

- 业绩基准 / IR / 夏普 / 选股 / 择时 / α-IR — 单独后续 PRD 与 implement。

## Notes

- 第一阶段涉及文件：
  - 后端：`config/funds_stock.yaml`（新建）、`src/data/achievement_fetcher.py`（新建）、`src/db/models.py`（加 `FundAchievementRank`）、`src/db/migrations/`（加 alembic 迁移）、`src/services/refresh_service.py`（分支）、`src/api/routes.py`（新接口 `/funds_stock/stocks`）、`tests/`。
  - 前端：`apps/fund-select/src/app/funds/stock/page.tsx`（新建）、复用现有组件 + 类型 + useFilters。
- 第二阶段不写代码；后续单独 task。
- 立项前请先 review PRD。
