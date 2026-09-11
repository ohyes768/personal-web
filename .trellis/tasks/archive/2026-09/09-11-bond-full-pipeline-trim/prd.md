# 债基全量刷新流程精简（跳过 L4 risk + L5 achievement）

## 目标

债基·市场 tab 的全量刷新流程中，L4（业绩比较基准 + 风险指标）和 L5（同类排名）产出的
数据**前端债基侧完全不消费**：

- **L4 6 指标**（sharpe / ir / alpha / gamma / alpha_ir / excess_3y）：`RiskMetricsGrid`
  组件**仅**被 `RowDetailDrawer.tsx`（股基详情页）import，
  `RowDetailDrawerBond.tsx` 完全没 import
- **L5 同类排名**（`fund_achievement_rank`）：只有 `RowDetailDrawer.tsx`（股基）消费
  `detail.achievement_ranks`，债基详情页 / 列表页 / 筛选器均不消费

但 L3（日频净值）必须保留：`max_dd_3y` 是债基筛选维度
（`discovery-bond/page.tsx:77` 有 `max_dd_3y`），且 nav 数据是 1y/3y 涨幅、近期回撤计算基础。

改造后债基 4 阶段流水线（L0 → L1 → L2 → L3），单次刷新 ~100 分钟 → ~30 分钟；
股基维持 6 阶段不变。

## 数据源速查（已核实，非"代码注释复述"）

| 阶段 | 数据源 | 耗时 | 债基用？ |
|---|---|---|---|
| L0 universe | akshare `fund_name_em` | 5s | ✓ |
| L1 rank | akshare `fund_open_fund_rank_em` | 50s | ✓ |
| L2 size | **雪球优先 + 东财 msm fallback** | 8 min | ✓ |
| L3 nav | akshare `fund_open_fund_info_em` | 22 min | ✓（max_dd_3y 依赖） |
| L4 risk | 东财 benchmark + risk_service | 44 min | **✗** |
| L5 achievement | 雪球 `fund_individual_achievement_xq` | 22 min | **✗** |

## 改动范围

### 后端

1. **`backend/fund-select/src/services/market_full_pipeline.py`**
   - 给 `refresh_market_full_sync` 加参数 `pipeline_profile: str = "stock"`，
     取值 `"stock"` / `"bond"`；其他值拒绝（ValueError，路由层把控，不依赖隐式默认）
   - 内部维护 `_BOND_STAGES = ("L0_universe", "L1_rank", "L2_size", "L3_nav")` 常量
   - profile == "bond" 时：跳 `_stage_l4`、`_stage_l5`；保留前 4 阶段
   - main_run.total 从写死的 `len(codes) * 6` 改成 `len(codes) * len(active_stages)`
   - `stage_results` / 日志 / 阶段命名 保持原样（债基任务 status 显示 4 个 stage key 即可）
   - docstring 重写：明确 6 vs 4 阶段差异 + profile 含义

2. **`backend/fund-select/src/api/routes.py:444` `discovery_bond_full_refresh`**
   - 在 background.add_task 调 `refresh_market_full_sync` 时传 `pipeline_profile="bond"`

3. **不动**：
   - `market_risk_refresh.refresh` / `market_achievement_refresh.refresh` 函数本身
     （保持可独立调用，scheduler / 其他入口不破坏）
   - `risk_service.refresh_fund_risks` / `compute_risk_metrics`（共享计算逻辑不动）
   - 股基路由 `discovery_stock_full_refresh`（保持默认 profile="stock"，6 阶段不变）

### 前端

不动。前端只接 3 个 query 参数（min_ret_3y/min_size_yi/min_mgr_exp）和 task_id；债基刷新
接口签名、轮询接口、对话框、locked 字段全部不变。

### 测试

4. **`backend/fund-select/tests/test_market_full_pipeline.py`**（如不存在则新建）
   - 测 1：profile="bond" 时 `_stage_l4` / `_stage_l5` **不被调用**（mock）
   - 测 2：profile="stock" 时 6 阶段全跑（回归）
   - 测 3：profile 默认值是 "stock"（向后兼容旧调用点）
   - 测 4：main_run.total 按 profile 动态计算（bond=4，stock=6）
   - 测 5：profile 取非法值 → ValueError

## 非范围（out of scope）

### 债基三分法（`/funds/bond` 老路径）不在本任务范围

债基·市场 tab（`/funds/discovery-bond`）与债基三分法（`/funds/bond`）是**两套独立的
refresh pipeline**，不是同一个 pipeline 接不同 universe：

| 维度 | 债基·市场（新） | 债基三分法（老） |
|---|---|---|
| 入口 | `refresh_market_full_sync` (`market_full_pipeline.py:149`) | `refresh_configured_funds_sync` (`scheduler/tasks.py:42`) |
| Universe 来源 | `ak.fund_name_em()` 全市场 | `config/funds.yaml` 手工名单 |
| 循环模式 | 6 阶段流水线 + 分阶段重算 codes | for code: 单只 `snapshot_fund` |
| 主要写表 | `market_fund_rank` / `market_nav` / `fund_risk_metrics` / `fund_achievement_rank` | `funds` / `FundFees` / `FundHoldingsBond` / `FundPerformance` |

老债基三分法**本来就不跑 L4/L5**：
- `snapshot_fund` 默认 `fetch_ranking=False`（`refresh_service.py:60` 注释）→ 不写
  `fund_achievement_rank`
- `refresh_configured_funds_sync` 不调 `benchmark_refresh.refresh`（仅
  `refresh_stock_funds_sync` 在 line 159 调，债基老路径无此调用）→ 不写
  `fund_risk_metrics`
- 老债基路径算的是 `compute_performance(nav)`（基于净值的 1y/3y/5y 收益和回撤），
  不是 `risk_service.compute_risk_metrics` 的 Sharpe/IR/alpha

所以老路径没有"浪费的阶段可精简"。把两套 pipeline 合并成一个 profile-driven pipeline
属于更大的架构重构，超出本任务。

### 其他非范围

- 债基详情页**补回** L4/L5 数据展示（用户决策：债基不要风险拆解区，保留简洁）
- L1 rank fetcher 内部用 `symbols=["股票型", "混合型", "债券型", "指数型", "QDII"]`
  是全市场一次拉，债基也能命中，**不动**
- L3 nav 写 `max_dd_3y` 是 nav 服务的现有功能，**不新加字段**
- `benchmarks_refresh.refresh`（独立 scheduler 路径）**不动**——它是股基 tab 用的
- 调度任务 `scheduler/tasks.py` 如有债基全量刷新入口，新增 `pipeline_profile="bond"` 传参
- 不重构 `refresh_market_full_sync` 内部为配置驱动；保持当前的 if/elif 显式分支

## 设计决策

D1：用 `pipeline_profile` 字符串而非 `skip_risk: bool, skip_achievement: bool` 两个开关。
   理由：profile 语义更紧，债基侧未来若有更多差异（比如 nav 频率不同）也好扩；
   两个独立 bool 容易被错误组合（如 `skip_risk=False, skip_achievement=True` 跑出半成品）。

D2：profile 默认值 `"stock"` 而非 `"bond"`。
   理由：现有股基路由不传 profile，靠默认值保持 6 阶段行为不变；
   显式债基路由传 `"bond"` 走 4 阶段路径。

D3：`stage_results` 不删除债基路径下的 L4/L5 key，写成 `{"skipped": "..."}` 或干脆不写。
   倾向：**不写**（stage_results 是执行结果字典，没跑不存在的阶段没必要造假）。
   前端轮询拿到的 RefreshRun 仍然按 4 阶段算 total/completed/failed。

D4：不引入新数据库 migration，不动 fund_risk_metrics / fund_achievement_rank 表结构。
   历史数据保留即可，下次债基全量刷新跑完后这两个表的债基行仍是过期值；
   这是可接受的（债基前端不读），且降低风险。

## 验收

| # | 验证项 | 验证方式 |
|---|---|---|
| A1 | profile="bond" 跑完全量刷新，**实际耗时 ≤ 35 分钟** | 后端日志 `stage_results` 只含 L0/L1/L2/L3 |
| A2 | 跑完后 `fund_risk_metrics` / `fund_achievement_rank` 表债基行**未被改写**（可选：清空时间戳后跑一次比对） | SQL 比对 |
| A3 | 股基路由 `discovery_stock_full_refresh` 仍跑 6 阶段，未回归 | 后端日志包含 L0-L5 全部 6 个 stage key |
| A4 | 债基路由 main_run.total = codes × 4；股基 = codes × 6 | `get_full_refresh_status` 接口 |
| A5 | profile="bond" 完成后，`funds` 表债基行的 size_yi / mgr_experience_years / max_dd_3y 已更新 | DB 查询债基样本 |
| A6 | 债基详情页 / 列表页 UI 无变化（不展示 Sharpe/IR/alpha 不变） | dev 手动 + diff |
| A7 | 新增/更新 pytest 用例通过 | `pytest tests/test_market_full_pipeline.py -v` |
| A8 | 后端 pytest 全套通过 | `pytest tests/ -v` |

## 关键文件

- `backend/fund-select/src/services/market_full_pipeline.py:149,286,295` — pipeline 主体
- `backend/fund-select/src/api/routes.py:444` — 债基路由入口
- `apps/fund-select/src/lib/types.ts` / `apps/fund-select/src/app/discovery-bond/page.tsx` —
  前端不动但要在 PR 描述里明确无变化

## 风险 / 回滚

- 风险点 1：scheduler/tasks.py 若有债基全量刷新入口没传 profile，靠默认 `"stock"` 跑
  6 阶段 → 债基又被写废 66 分钟。**先 grep 确认 scheduler 是否调用 `refresh_market_full_sync`**
- 风险点 2：未来若有第三类 universe（比如货币/FOF），需要扩 profile。当前设计保留扩展位
- 回滚：把债基路由 `pipeline_profile="bond"` 删掉即回到 6 阶段；profile 默认值保留 `"stock"`

## 关联任务

- `09-11-bond-full-refresh-default-10pct` — 独立任务，不合并到本任务（一个改前端默认值，一个改后端流程）