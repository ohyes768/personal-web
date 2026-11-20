# 执行计划

原则：**先加后改，每步可独立验证**。注册表与迁移分开提交；迁移做完先跑一遍 000300 的回归，再动估值。

## 0. 基线（先做，不可省）

- [ ] `cd backend/index-trends && uv run python -m pytest tests/ -v` — 记录当前通过数作为基线
- [ ] 备份现有库：`VACUUM INTO 'data/backup-before-006-<日期>.db'`
- [ ] 记录 000300 的不变量，迁移后逐条比对：`weekly_bars` 行数、最新 `weekly model_id`、`data_cutoff_week`、`snapshot_id`

## 1. 指数注册表（纯新增，零风险）

- [ ] 新建 `src/core/indexes.py`：`IndexDef` + `INDEXES` + `BY_CODE`
- [ ] `trend_service.py` 的 `INDEX_CODE/SYMBOL/INDEX_NAME` 改为从注册表取（先用 `BY_CODE["000300"]` 填位，保持单指数行为）
- [ ] `earliest` 断言改读 `idx.earliest_weekly`
- [ ] 验证：`pytest tests/` 仍全绿（行为未变）

## 2. 存储多指数迁移

- [ ] `store.py` 加迁移 `006_multi_index`：`monthly_bars`、`daily_quotes`、`weekly_bars`、`data_meta`、`weekly_data_meta`、`valuation_fetch_meta` 六张表重建，主键前置 `index_code`，旧数据回填 `'000300'`
- [ ] 读方法加 `index_code` 参数（`load_monthly_bars`、`load_daily_quotes`、`load_weekly_bars`、`load_partial_weekly_bars`、`get_data_meta`、`get_weekly_data_meta`、`latest_valuation`…）
- [ ] 写方法加 `index_code` 参数（`upsert_monthly_bars`、`upsert_daily_quotes`、`publish_weekly_snapshot`、`publish_valuation`、`record_valuation_failure`、`set_data_meta`）
- [ ] 迁移后立刻比对第 0 步记录的四条不变量
- [ ] 验证：000300 的 `/api/indices`、`/status`、`/chart` 返回与迁移前逐字段一致

## 3. 创业板50 走势打通

- [ ] 刷新编排改为遍历 `INDEXES`；单个指数失败只记该指数状态
- [ ] 调度器（`services/scheduler.py`）同样遍历；日志区分指数
- [ ] 手工触发 399673 刷新，检查：周K覆盖到 2014-06、模型 `fit_start` 落在 2014 年、位置百分比可算
- [ ] 验证：`GET /api/indices/399673/status?model=trailing_10y_weekly` 有值；000300 数据未被动过

## 4. 估值双指标

- [ ] `lixinger.py`：`METRIC_SPECS`（pe_ttm / pb）、一次请求带 4 个指标、解析出 `(metric, value, percentile_ratio)`
- [ ] 新增 `index_valuation_history` 表 + 首次 10 年回填（每指数每次请求一行区间）
- [ ] `ValuationService` 加 `index_code` 参数；`ValuationRegistry` 挂在 `app.state`
- [ ] `valuation_fetch_meta` 按 `(index_code, metric)` 记失败，互不污染
- [ ] 验证：399673 的 PB 与 PE 分位都 `state=ok`；无 Token 时两者 `disabled`

## 5. 接口

- [ ] `_require_supported_index` 改查 `BY_CODE`，404 文案列支持代码
- [ ] `valuation` 响应加 `metrics` 映射，保留 PE 平铺字段（不回归）
- [ ] 新增 `/api/indices/{code}/valuation/history?metric=pb|pe_ttm`（metric 白名单，非法 400）
- [ ] 验证：两个指数的 `status` 返回互不干扰；非法 metric 返回 400

## 6. 前端

- [ ] `lib/api.ts`：四个函数加 `code` 参数，默认 `000300`
- [ ] 页面加指数切换（沪深300 / 创业板50）
- [ ] 估值卡：PB 分位主、PE 分位辅；曲线图按 metric 切换，带 20/50/80 参考线
- [ ] 状态降级照旧：`disabled` / `stale` / `error` 各自可见，不显示假 0

## 7. 收尾验证

- [ ] `cd backend/index-trends && uv run python -m pytest tests/ -v`（新增：多指数隔离、PB 解析、metric 白名单、迁移回填）
- [ ] `cd apps/index-trends && pnpm lint && pnpm exec tsc --noEmit`
- [ ] 起 8100 + 3010，人工看两个指数的图与分位
- [ ] `.trellis/spec` 是否需要补：多指数存储契约、估值 metric 维度

## 风险点与回滚

| 位置 | 风险 | 回滚 |
|---|---|---|
| 第 2 步迁移 | 主键重建写坏数据 | 迁移单事务 + 第 0 步 `VACUUM INTO` 备份；失败直接换回备份文件 |
| 第 3 步刷新编排 | 一次刷新两个指数、任一异常拖垮整体 | 逐个 try，失败记该指数状态；断言 000300 不受影响 |
| 第 4 步首次回填 | 理杏仁单请求区间过大被拒 | 降级为分段回填（每次 1 年） |
| 第 6 步前端 | 一次性改多处调用 | `code` 参数默认值兜底 |

**提交切分建议**：① 注册表 + 迁移 + 多指数行情（后端，一个提交，含测试）② 估值双指标 + 接口（第二个）③ 前端（第三个）。
