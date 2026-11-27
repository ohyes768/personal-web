# 执行计划（as-built 收尾版）

> **口径变更（2026-11-20，用户明确）**：创业板50 **不做回归通道**，但**要显示价格走势**。
> 采行情（周K/日线）并出价格折线，不拟合通道；通道类接口对 399673 返回 409；价格走 `/prices`，估值走 `/valuation`。
> 下文按最终口径回填，原计划里「创业板50 出通道/模型」的部分已作废。

原则：**先加后改，每步可独立验证**。注册表与迁移分开提交；迁移做完先跑一遍 000300 的回归，再动估值。

## 0. 基线（先做，不可省）

- [x] `cd backend/index-trends && uv run python -m pytest tests/ -v` — 记录当前通过数作为基线
- [x] 备份现有库：`VACUUM INTO 'data/backup-before-006-<日期>.db'`
- [x] 记录 000300 的不变量，迁移后逐条比对：`weekly_bars` 行数、最新 `weekly model_id`、`data_cutoff_week`、`snapshot_id`

## 1. 指数注册表（纯新增，零风险）

- [x] 新建 `src/core/indexes.py`：`IndexDef` + `INDEXES` + `BY_CODE`（000300 沪深300 / sh000300 / 2005-04；399673 创业板50 / sz399673 / 2014-06-16，`has_channel=False`）
- [x] `trend_service.py` 的 `INDEX_CODE/SYMBOL/INDEX_NAME` 改为从注册表取
- [x] `earliest` 断言改读 `idx.earliest_weekly`
- [x] 验证：pytest 仍全绿（行为未变）

## 2. 存储多指数迁移

- [x] `store.py` 加迁移 `006_multi_index`：六张表重建，主键前置 `index_code`，旧数据回填 `'000300'`
- [x] 读方法加 `index_code` 参数（`load_monthly_bars`、`load_daily_quotes`、`load_weekly_bars`、`load_partial_weekly_bars`、`get_data_meta`、`get_weekly_data_meta`、`latest_valuation`…）
- [x] 写方法加 `index_code` 参数（`upsert_monthly_bars`、`upsert_daily_quotes`、`publish_weekly_snapshot`、`publish_valuation`、`record_valuation_failure`、`set_data_meta`）
- [x] 迁移后立刻比对第 0 步记录的四条不变量
- [x] 验证：000300 的 `/api/indices`、`/status`、`/chart` 返回与迁移前逐字段一致

## 3. 创业板50 行情打通（价格有、通道无）

- [x] 刷新编排遍历 `INDEXES`；`compute_models` 对 `has_channel=False` 的指数直接返回空模型列表（只落周K与日线）
- [x] 调度器同样遍历；单个指数失败只记该指数状态
- [x] 通道类接口（`/chart`、`/history`）对无通道指数返回 409，文案说明「只有价格走势与估值分位」
- [x] `current_status` 对无通道指数返回 `has_channel=false` + 价格字段（`close`/`price_as_of`），通道字段一律不出现
- [x] 验证：399673 `/prices` 有数据、`/chart` `/history` 409；000300 通道行为未变

## 4. 估值双指标

- [x] `lixinger.py`：`METRIC_SPECS`（pe_ttm / pb）、一次请求带 4 个指标、解析出 `(metric, value, percentile_ratio)`
- [x] 新增 `index_valuation_history` 表 + 首次 10 年回填（每指数每次请求一行区间）
- [x] `ValuationService` 加 `index_code` 参数；`ValuationRegistry` 挂在 `app.state`
- [x] `valuation_fetch_meta` 按 `(index_code, metric)` 记失败，互不污染
- [x] 验证：399673 的 PB 与 PE 分位都 `state=ok`；无 Token 时两者 `disabled`

## 5. 接口

- [x] `_require_supported_index` 改查 `BY_CODE`，404 文案列支持代码；新增 `_require_channel_index` 负责 409
- [x] `valuation` 响应加 `metrics` 映射，保留 PE 平铺字段（不回归）
- [x] 新增 `/api/indices/{code}/valuation/history?metric=pb|pe_ttm`（metric 白名单，非法 400）
- [x] 新增 `/api/indices/{code}/prices`（价格走势，不需要 model）
- [x] 验证：两个指数的 `status` 返回互不干扰；非法 metric 返回 400

## 6. 前端

- [x] `lib/api.ts`：四个函数加 `code` 参数，默认 `000300`
- [x] 页面加指数切换（沪深300 / 创业板50）；无通道指数自动落到「估值分位」视图
- [x] 估值卡：PB 分位主、PE 分位辅（`d07162e8` 合并为一张图，`16777bb5` 改为只画指数点数、分位悬浮查表）
- [x] 状态降级照旧：`disabled` / `stale` / `error` 各自可见，不显示假 0

## 7. 收尾验证

- [x] `cd backend/index-trends && uv run python -m pytest tests/ -v` → **237 passed**
- [x] `cd apps/index-trends && npx tsc --noEmit` 通过；`pnpm build` 通过（该 app 无 lint 脚本）
- [x] 生产实测（容器直连 `index-trends-backend:8095`→8100 + 浏览器 `/index-trends`）：见下节
- [x] `.trellis/spec` 已补：`backend/index-trends/backend/valuation-contract.md` 记录注册表、无通道指数、PB/PE 双指标口径

## 8. 收尾复核（2026-11-27，生产环境）

线上容器直连实测，非本地推断：

| 验收项 | 实测结果 |
|---|---|
| `GET /api/indices` | 2 条：000300（has_channel=true, 起点 2005-04-04）、399673（has_channel=false, 起点 2014-06-16） |
| `GET /api/indices/399673/status?model=trailing_10y_weekly` | `available=true`、`has_channel=false`、`reason=null`；`valuation.state=ok` |
| `valuation.metrics` | `pb_mcw`（PB 3.55，percentile 3.3%，as_of 2026-11-26）、`pe_ttm_mcw`（PE 19.92，percentile 0.0%，as_of 2026-11-26） |
| `GET /api/indices/399673/chart` / `/history` | 均 409「创业板50不提供回归通道，只有价格走势与估值分位」 |
| `GET /api/indices/399673/valuation`（不带 model） | 200，两条分位齐全 |
| `GET /api/indices/399673/prices` | close=2183.39 @2026-11-26，20 根周线，最新一根 partial=true |
| `GET /api/indices/000300/prices` | close=3900.55 @2026-11-26 → 两指数数值独立、数据都在更新 |
| 生产库 | `weekly_bars`：000300 1104 行 / 399673 638 行；`daily_quotes`：340 / 325；`weekly_models` 仅 000300（12）；`valuation_fetch_meta` 每指数 2 行（PB/PE 各一） |
| 部署一致性 | 容器内 5 个后端源文件与仓库 HEAD **逐字节相同** |
| 页面 | 指数切换「沪深300 / 创业板50」可用；创业板50 自动进「估值分位」视图，显示最近收盘 2183.39 + PB 分位 3.3% + PE 分位 0.0%，价格折线 2016-09-30→2026-11-26，脚注「不拟合回归通道」 |

**与 PRD 字面不一致处（实现口径变更，非缺陷）**：PRD AC2 写 `available=false`、`reason=valuation_only`；
实际实现为「有日线即 `available=true`、`reason=null`、通道字段一律不出现」（`has_channel=false` 承载语义）。
对应 2026-11-20 用户范围修正：无通道 ≠ 无数据。

## 风险点与回滚

| 位置 | 风险 | 回滚 |
|---|---|---|
| 第 2 步迁移 | 主键重建写坏数据 | 迁移单事务 + 第 0 步 `VACUUM INTO` 备份；失败直接换回备份文件 |
| 第 3 步刷新编排 | 一次刷新两个指数、任一异常拖垮整体 | 逐个 try，失败记该指数状态；断言 000300 不受影响 |
| 第 4 步首次回填 | 理杏仁单请求区间过大被拒 | 降级为分段回填（每次 1 年） |
| 第 6 步前端 | 一次性改多处调用 | `code` 参数默认值兜底 |

## 提交

| 提交 | 内容 |
|---|---|
| `42cd6909` | 支持多指数（新增创业板50）与 PB/PE 双指标分位（后端 + 存储 + 迁移） |
| `33687801` | 前端加指数切换与分位走势图 |
| `237d0196` | 创业板50 只做 PB/PE 分位，不再提供走势通道（口径变更） |
| `5bd29829` | 创业板50 显示价格走势（不拟合通道），分位独立计算 |
| `c087f457` | 估值 tab 也显示价格走势图 |
| `d07162e8` | 估值页价格走势与分位合并为一张图 |
| `16777bb5` | 估值图只画指数点数，PB/PE 分位改为悬浮查表 |

## 提交与归档

- [x] 功能提交（后端 + 前端 + 测试 + spec + 任务目录）——见上表
- [x] 部署上线（`index-trends` 前后端，生产库已含 399673 数据）
- [x] 任务目录归档与 journal 记录
