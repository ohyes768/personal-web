# fund-select 新增「市场筛选」tab 页（债基·市场 / 股基·市场）

## Goal

在 fund-select 新增 2 个并列 tab，从 akshare 全市场基金池筛债基/股基：

- `/funds/discovery-bond` — 债基·市场（fund-select 顶部导航追加入口）
- `/funds/discovery-stock` — 股基·市场

与现有 `/funds/bond` 和 `/funds/stock`（基于本地 `funds.yaml` / `funds_stock.yaml` 名单）并列共存；老 tab 行为不变。

## Background

### 现有架构

| 维度 | 现状 |
|---|---|
| 名单来源 | `backend/fund-select/config/funds.yaml`（债基 ~31 只）、`funds_stock.yaml`（股基 ~30 只），手工维护 |
| 拉取流程 | `scheduler/daily_refresh.py` 遍历 yaml 代码 → 逐只 `fund_basic_fetcher.fetch_basic()` → upsert Fund 表 |
| 筛选后端 | `FilterService._screen(kind, ...)` 按 `kind="bond"/"stock"` 走 `resolve_universe_codes()` 读 yaml |
| 筛选前端 | `apps/fund-select/src/app/{bond,stock}/page.tsx` + `useFundList/useStockFundList` + `FundsHeader` |
| 数据表 | `funds / fund_performance / fund_fees / fund_holdings_bond / fund_risk_metrics / fund_achievement_rank / fund_benchmark` |
| 字段 `Fund.fund_type` | **雪球 type_desc（细粒度）**，如「中长期纯债 / 偏股混合 / 被动指数」 |

### akshare 全市场接口（已调研）

`ak.fund_name_em()` 一次性返回约 1 万只全市场基金：
- 字段：`基金代码 / 拼音缩写 / 基金简称 / 基金类型 / 拼音全称`
- `基金类型` 是**粗粒度**枚举：`债券型 / 股票型 / 混合型 / 货币型 / 指数型 / QDII / FOF / 定开债券 / ...`
- 来源：天天基金网 fundcode_search.js，单次 HTTP 拉取，无参数

二级分类（"中长期纯债 / 短期纯债 / 可转债"）需逐只调雪球 `fund_individual_basic_info_xq` 才能取到——1 万只逐只调用预计 30+ 分钟，超出 MVP 范围。**MVP 仅用粗分类**。

### 关键问题：Fund.fund_type 已是细粒度

现有 `Fund.fund_type` 存的是雪球细分类（"中长期纯债"），而 akshare 给的是粗分类（"债券型"）。两者语义不同：
- 不能直接覆盖现有 `fund_type`（会破坏 stock/bond 老 tab 的展示）
- 新增 `Fund.market_type` 字段单独存 akshare 粗分类，老 tab 不受影响

## Requirements

### 功能需求

#### 后端

- **R1 新增 fetcher：`market_universe_fetcher.py`**
  - 调 `ak.fund_name_em()` 一次拉全市场
  - 过滤「基金简称」明显是无效的（如空名）
  - 返回 DataFrame `[code, name, market_type]`
  - 失败抛异常（外层调度重试）

- **R2 新增 refresh service：`market_universe_refresh.py`**
  - 拉 `market_universe_fetcher` → upsert `Fund` 表
  - 仅更新 `name / market_type / updated_at`，不触碰 `fund_type / is_active / 业绩数据`
  - 同一 code 已存在：只覆盖 `name / market_type / updated_at`
  - 新增 code：插入一行，`is_active=True`、`fund_type=""`、`market_type=<akshare 值>`
  - **不在 refresh 中改 is_active**（清盘判断需要业绩停更证据，MVP 不做）

- **R3 新增筛选接口**
  - `GET /api/funds/discovery-bond/screen` — 宇宙 = `market_type IN ('债券型', '定开债券')`
  - `GET /api/funds/discovery-stock/screen` — 宇宙 = `market_type IN ('股票型', '指数型', '混合型', 'QDII')`
  - 复用现有 `_screen()`，新增参数 `market_types: list[str] | None`
  - 复用现有 4 维度筛选（min_age / min_size_yi / max_dd_3y / min_mgr_exp）+ min_sharpe + exclude_qdii + 排序
  - **新增筛选维度：`market_type` 多选**（默认 = 该 tab 全部类型；用户可缩窄）
  - 复用 `get_detail`、`refresh/status`

- **R4 新增 refresh 端点**
  - `GET /api/funds/discovery-bond/refresh` — 触发市场名单刷新（拉 ak.fund_name_em → upsert Fund 表）
  - `GET /api/funds/discovery-bond/refresh/status` — 复用 `RefreshRun` 表

- **R5 数据库 schema 变更**
  - `funds` 表新增列：`market_type VARCHAR(64) NULL`（雪球 `fund_type` 字段不受影响）
  - 新增 migration：`backend/fund-select/migrations/xxx_add_market_type.sql` 或在 `db/session.py` 启动时自动 `ALTER TABLE`（择一）

- **R6 定时调度**
  - 在 `scheduler/tasks.py` 新增 `refresh_market_universe_sync()`
  - 在 `scheduler/daily_refresh.py` 接入：每天早上 06:30 跑一次（早于现有 yaml 刷新）
  - 复用 `RefreshRun` 表记录进度

#### 前端

- **R7 新增 2 个页面**
  - `apps/fund-select/src/app/discovery-bond/page.tsx`
  - `apps/fund-select/src/app/discovery-stock/page.tsx`
  - 复用 `FundTable / FilterChipBar / CompareDrawer / CompareFloatingBar / RowDetailDrawer`（股票 tab 用 stock 版本 Drawer，债基 tab 用 bond 版本 Drawer）

- **R8 `FundsHeader` 扩展**
  - `active` 类型扩展：`'bond' | 'stock' | 'discovery-bond' | 'discovery-stock'`
  - tab 顺序：`债基 | 股票 | 债基·市场 | 股基·市场`
  - 标题：discovery-bond → "债券基金·市场"、discovery-stock → "股票基金·市场"
  - RefreshStatusPopover 路径：`/api/funds/discovery-{kind}/refresh` 与 `/status`

- **R9 筛选面板扩展**
  - 新增 `marketType` 多选组件（chip 多选）
  - 各 tab 默认 market_type：discovery-bond → `['债券型', '定开债券']`、discovery-stock → `['股票型', '指数型', '混合型', 'QDII']`
  - 写入 URL：`?market_type=债券型,定开债券`（CSV）

- **R10 API client 扩展**
  - `apps/fund-select/src/lib/api.ts` 新增 `discoveryBondApi` / `discoveryStockApi`
  - 复用 `screen / getDetail / refresh / getRefreshStatus`

- **R11 catch-all 代理不动**
  - 现有 `apps/fund-select/src/app/api/funds/[...path]/route.ts` 已能转发任意路径，无需改

### 非功能需求

- **N1 老 tab 不回归**：bond/stock 页面、`funds.yaml`/`funds_stock.yaml` 解析、`_screen(kind='bond'/'stock')` 路径全不变
- **N2 性能**：全市场 ~1 万只；bond universe 估计 ~3000 只、stock universe 估计 ~5000 只。SQL 4 join 后 < 3s
- **N3 拉取限频**：market universe refresh 单次 HTTP 即可（ak.fund_name_em 一把拉完），不需分布式；失败重试 3 次
- **N4 不引入新依赖**：akshare / SQLAlchemy / FastAPI 已齐
- **N5 中文注释 / 函数命名延续项目风格**（中文 docstring + snake_case）

## Data Sources & Boundaries

### 数据源

| 数据 | 来源 | 频率 |
|---|---|---|
| 全市场基金名单 | `ak.fund_name_em()` | 每日 06:30 |
| 单只业绩 / 费率 / 持仓 / 风险指标 | 现有 yaml refresh 流程 | 每日 07:00（现状） |

### 数据边界

- **市场 tab 不会拉单只业绩数据**（保持刷新解耦）；用户进 tab 时只看到已在库的基金
- 市场 tab 里的基金若没有 yaml 名单 → 没业绩数据 → 显示空指标；这没问题（与 stock tab 现状一致：表中没有 FundPerformance 行的就不显示 ret）
- MVP 不做"清盘判断"，akshare 拉到的全市场基金都默认 `is_active=True`

## Out of Scope

- ❌ 二级分类（"中长期纯债 / 短期纯债 / 可转债 / 被动债指 / 偏股混合"）逐只拉雪球
- ❌ 市场 tab 与现有 stock/bond tab 联动去重
- ❌ 自动判断基金清盘（is_active 自动置 False）
- ❌ 详情页 RowDetailDrawer 改造（市场 tab 复用现有 drawer，不加新字段）
- ❌ 实时行情 / 净值刷新（market tab 仍走现有 daily_refresh）
- ❌ 缓存层 / Redis
- ❌ FOF / 货币型 / 其他 新增独立 tab（不在本任务范围）

## Acceptance Criteria

### 后端

- [ ] **AC1** `ak.fund_name_em()` 拉到的全市场基金数 ≥ 8000（当前中国公募基金总数）
- [ ] **AC2** 跑完 `refresh_market_universe_sync()` 后，`SELECT COUNT(*) FROM funds WHERE market_type IS NOT NULL` ≥ 8000
- [ ] **AC3** 跑完 refresh 后，`market_type='债券型'` 的基金数 ≥ 1000，`market_type='股票型'` ≥ 500
- [ ] **AC4** `GET /api/funds/discovery-bond/screen` 返回 `total` 等于 `market_type IN ('债券型', '定开债券')` 的活跃基金数
- [ ] **AC5** `GET /api/funds/discovery-stock/screen?min_size_yi=10&sort=ret_3y&order=desc` 返回按 ret_3y 降序的结果，ret_3y NULL 排尾部
- [ ] **AC6** `GET /api/funds/discovery-bond/screen?market_type=债券型` 等价于默认 universe 缩窄到「债券型」单选（等价 SQL: `market_type='债券型'`）
- [ ] **AC7** 现有 `GET /api/funds/screen` 与 `GET /api/funds/stock/screen` 返回不变（手工 curl 验证 total 一致）
- [ ] **AC8** `funds` 表 schema 变更后，老 YAML refresh 仍能跑通（`is_active=True` 命中 yaml 名单基金数 = 现状）

### 前端

- [ ] **AC9** 访问 `/funds/discovery-bond` 页面渲染出顶部 4 tab，激活「债基·市场」
- [ ] **AC10** 切换 tab 到 `/funds/discovery-stock` 激活「股基·市场」
- [ ] **AC11** 4 个 tab 的 URL 都能正常打开，老 tab `/funds/bond` 与 `/funds/stock` 不报错
- [ ] **AC12** 市场 tab 顶部显示基金总数（如 "共 3241 只"）
- [ ] **AC13** 筛选维度（min_age / min_size_yi / max_dd_3y / min_mgr_exp）变更后表格刷新，结果数变化正确
- [ ] **AC14** market_type 多选 chip 可移除 / 重新添加，URL query 同步
- [ ] **AC15** 点击「刷新」按钮触发后端 refresh，弹窗显示进度（复用 RefreshStatusPopover）

### 数据

- [ ] **AC16** 单次 `refresh_market_universe_sync()` 耗时 < 60s（ak.fund_name_em 一次 HTTP + ~1 万次 upsert）
- [ ] **AC17** refresh 失败时 `RefreshRun.status='error'`、`errors` 记录原因，不影响主流程
- [ ] **AC18** akshare 接口异常（网络/限流）时，refresh 任务记录失败原因后退出，下次调度再试

### 测试

- [ ] **AC19** `pytest backend/fund-select/tests/test_market_universe.py` 通过（fetcher 单测 + refresh 单测）
- [ ] **AC20** `pytest backend/fund-select/tests/test_filter_service.py` 通过（market universe 筛选 + 多 market_type 缩窄）
- [ ] **AC21** `pnpm --filter fund-select lint` 无新增 error
- [ ] **AC22** `pnpm --filter fund-select build` 通过

## Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| `ak.fund_name_em()` 偶发限流 | refresh 加 try/except + 重试 3 次，失败记录到 RefreshRun.errors |
| 全市场 1 万只 SQL 4 join 慢 | 仅 outerjoin，不强制 NOT NULL；如慢可加分页或 `LIMIT 5000` 兜底（MVP 不分页） |
| `Fund.market_type` 与 `Fund.fund_type` 语义混淆 | 字段名严格区分；新代码只用 market_type；老代码不动 |
| akshare 接口返回字段名变化 | fetcher 写死列名 `基金代码 / 基金简称 / 基金类型`，用 try/except 包一层 |
| 4 tab 顶部导航在小屏溢出 | FundsHeader 现有 `flex` 已能容下 4 个 chip；如溢出加 `overflow-x-auto` |
| 市场 tab 没有业绩数据的基金噪音 | 不在 filter_service 屏蔽空业绩，让表格自然显示 NULL，与 stock tab 现状一致 |

## Notes

- PRD 不含技术设计（见后续 `design.md`）
- PRD 不含执行计划（见后续 `implement.md`）
- 实现顺序建议：先 R5（schema）+ R1（fetcher）+ R2（refresh）→ R3/R4（API）→ R10（前端 API client）→ R7/R8/R9（页面）→ R6（定时）
- 复核点：R5 schema 变更前确认生产数据库 funds 表无 `market_type` 列；R2 refresh 前确认 yaml refresh 已停止（避免冲突）
