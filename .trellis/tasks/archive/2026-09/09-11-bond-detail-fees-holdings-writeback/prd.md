# 债基·市场 tab 详情页自给自足：新套补写 FundFees + FundHoldingsBond

## 目标

债基·市场 tab（`/funds/discovery-bond`）的详情页当前依赖老债基三分法（`/funds/bond`）写的
`FundFees` / `FundHoldingsBond` 表——也就是说：

- 列表数据是新套（v2 market pipeline）写的 → 全市场 2.8 万只筛债基
- 点开任何一只的详情数据是**老套（v1 yaml）**写的 → 手工名单 ~100-200 只

**只跑新套不跑老套时**：详情页的费率、债券持仓、经理公司都是空的。

目标：让新套也写 `FundFees` + `FundHoldingsBond`，详情页自给自足。复用现有 fetcher。

## 范围

### 后端

1. **`backend/fund-select/src/services/market_full_pipeline.py`**
   - 在 `pipeline_profile == "bond"` 路径下，L3 之后新增一个阶段（如 `_stage_l6_fees_holdings`）
   - **仅债基**：用 `market_subtype in DISCOVERY_BOND_SUBTYPES` 二次过滤 codes（理论上 L2
     之后已是债基 universe，但防御性再过滤一遍，注释说明"未来 profile 扩展时这层兜底"）
   - 复用 `snapshot_fund` 的 fetcher 调用 + `persist_snapshot` 的写表逻辑——直接 import 用，
     不重写字段映射
   - **并发**：`concurrent.futures.ThreadPoolExecutor(max_workers=5)`（东财反爬限流），
     参考 `market_nav_fetcher.MAX_WORKERS = 5` 的现有口径
   - 单只失败容错：try/except 包住，错误入账 `errors` 列表，不阻塞其他
   - **季报默认抓上一年报**：复用 `snapshot_fund` 内部 `holdings_year = str(ref.year - 1)`
     逻辑，传给 `fetch_bond_hold(code, year)`
   - `main_run.total` 在 profile="bond" 时 = `codes × 5`（L0/L1/L2/L3/L6），profile="stock"
     维持 `codes × 6`（L0-L5）

2. **`backend/fund-select/src/api/routes.py:444` `discovery_bond_full_refresh`**
   - 路由本身不动——pipeline 内部已按 profile 分支

3. **`backend/fund-select/src/services/refresh_service.py`** — **不修改**
   - `snapshot_fund` / `persist_snapshot` / `compute_performance` 全部不动
   - 新套只复用 fetcher 函数和写入函数，**不重写逻辑**

### 前端

0 改动。详情页 `fundApi.getDetail(code)` 接口和 DTO 不变。

### 测试

4. **`backend/fund-select/tests/test_market_full_pipeline.py`**
   - 测 1：profile="bond" 跑完后，`fetch_fees` 和 `fetch_bond_hold` 被调用次数 = codes 数
     （验证债基 universe 全部走新路径，不再依赖老套）
   - 测 2：profile="bond" 单只 fetch_fees 抛异常 → 该只失败、其余继续
   - 测 3：profile="bond" main_run.total = codes × 5（5 个 stage）
   - 测 4：profile="stock" 不调 fetch_fees / fetch_bond_hold（回归）
   - 测 5：profile="bond" `market_subtype` 不在 DISCOVERY_BOND_SUBTYPES 的 code 被过滤掉

## 非范围（out of scope）

- **老债基三分法（v1 yaml）下线**：本任务完成后老套仍可跑，作为兜底 / 交叉验证。
  下线是更大重构（v1 yaml 维护问题），等债基·市场刷新稳定后单独决策
- 详情页前端改造：本任务纯后端写表，前端 0 改动
- **季报抓取周期**：默认上一年报不切换为"本年最近可获取季报"，保持现状
- **缓存层**：`fetch_fees` / `fetch_bond_hold` 自带的 JSON 缓存机制不动
- **频控策略**：东财反爬问题按 5 worker 处理，**不引入 Redis / 全局限流**——保持轻量
- **stock tab**：不写 fees/holdings（`fetch_holdings=False` 是老路径现状）。本任务也不写

## 设计决策

D1：复用 `snapshot_fund` 和 `persist_snapshot`，不重写 fetcher 调用。
   理由：字段映射（`out["holdings"]`、`out["fees"]` → `FundFees`/`FundHoldingsBond` ORM）已有
   老路径实现，**直接 import 比复制代码更稳**。但 `snapshot_fund` 还会拉 basic/nav/performance
   （债基新套已写这些表），所以只调用 fetcher 函数（`fetch_fees` + `fetch_bond_hold` +
   `analyze_holdings`），不调整个 `snapshot_fund`。

D2：阶段放在 L6 而非合并进 L3。
   理由：L3 nav 是批量 akshare 接口（高效），fees/holdings 是单只东财反爬（要 worker 限流），
   IO 模式不同。独立阶段便于单独观察耗时和失败率。

D3：max_workers = 5 对齐 `market_nav_fetcher.MAX_WORKERS`。
   理由：东财反爬对单 IP QPS 敏感，5 worker 是历史经验值。

D4：失败仅入账 `errors`，不阻塞其他。
   理由：与 `refresh_configured_funds_sync` 老路径行为一致——单只失败重试 3 次后跳过。
   但新套用 worker 并发时不重试（避免长尾），单次失败即跳过，更激进。

D5：`pipeline_profile="bond"` 阶段序列为 L0/L1/L2/L3/**L6**——跳过 L4/L5。
   命名 L6 而非 L4_fees 避免和股基 L4/L5 混淆，也方便未来债基插入其他阶段时仍能编号。

## 验收

| # | 验证项 | 验证方式 |
|---|---|---|
| A1 | 只跑债基·市场全量刷新（不跑老套）后，详情页费率列 8 字段（`fee_buy_small`/`fee_redeem_lt7d`/.../`fee_service`）有值 | dev 手动点开 5 只样本详情 |
| A2 | 详情页债券持仓表有数据（持仓占比 / 债券代码 / 债券名称） | 同上 |
| A3 | 债基全量刷新总耗时 ≤ 40 分钟（30 分钟原精简 + 7 分钟 fees/holdings + buffer） | 后端日志 stage_results |
| A4 | 单只 fees/holdings 抓取失败不影响其他 | 后端日志 errors 列表 + 实际 fund 表写入数 |
| A5 | pytest 测试 5 条全过 | `pytest tests/test_market_full_pipeline.py -v` |
| A6 | 跑完后 DB 实际有债基 fees/holdings 行写入 | `SELECT count(*) FROM fund_fees WHERE code IN (SELECT code FROM funds WHERE market_subtype LIKE '债券型%' OR market_subtype LIKE '指数型-固收%')` 数值合理 |
| A7 | profile="stock" 不写 fees/holdings（回归） | 后端日志 + DB 行数比对 |
| A8 | 老套（v1 yaml）仍能独立跑，未破坏 | `refresh_configured_funds_sync` 单跑通 |

## 关键文件

- `backend/fund-select/src/services/market_full_pipeline.py` — 新增 `_stage_l6_fees_holdings`
- `backend/fund-select/src/services/refresh_service.py` — **只读复用** `fetch_fees` /
  `fetch_bond_hold` / `analyze_holdings` / `persist_snapshot`
- `backend/fund-select/src/data/fee_fetcher.py` — `fetch_fees` 不动
- `backend/fund-select/src/data/holdings_fetcher.py` — `fetch_bond_hold` 不动
- `backend/fund-select/src/data/market_subtype_map.py` — `DISCOVERY_BOND_SUBTYPES` 复用

## 风险 / 回滚

- 风险 1：东财反爬 5 worker 仍不够，5 分钟内全失败 → 临时降到 2 worker
- 风险 2：季报抓取某些债基返回空（东财季报接口问题）→ `fetch_bond_hold` 本就返回空列表，
  写表时跳过，详情页持仓显示空是已知降级
- 回滚：把 `_stage_l6_fees_holdings` 调用删掉即回到精简版（4 阶段），无 schema 破坏

## 关联任务

- `09-11-bond-full-pipeline-trim`（已 archive）：债基精简 4 阶段（无 fees/holdings）
- `09-11-bond-full-refresh-default-10pct`（**待 archive**：状态 in_progress 但代码已完成）

## 顺手待办

- 归档 `09-11-bond-full-refresh-default-10pct`（`c26cf3f` 已提交，状态未更新）