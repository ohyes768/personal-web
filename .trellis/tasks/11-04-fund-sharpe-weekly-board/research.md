# 代码证据（2026-11-04）

- `backend/fund-select/src/db/models.py:180`：FundRiskMetrics 以 code 为 PK，只有最新值，无历史表。
- `backend/fund-select/src/services/risk_service.py:121`、`:240`：近三年、样本至少 250 天；每次覆盖。as_of_date 是刷新日，实际样本尾日可能受基准 inner join 限制。
- `backend/fund-select/src/scheduler/weekly_refresh.py`：refresh_tab_sync 有 tab/job_id/trigger/run_id，调用相应采集器后写 JSONL。可接发布，但 classify_result 不能独自证明所有风险刷新成功。
- `backend/fund-select/src/scheduler/tasks.py`：stock 刷新基准/风险的错误放入 RefreshRun.errors，却未并入返回 failed。发布必须检查本轮风险证据，不能只看 returned failed==0。
- `backend/fund-select/src/services/market_full_pipeline.py` 和 `market_risk_refresh.py`：stock profile 计算风险，bond 跳过风险。市场先按收益/规模/经理预筛后才算风险，并非全市场都有本轮夏普。
- `backend/fund-select/src/services/filter_service.py:119`、`:167`：可复用股基筛选；默认分页 50，需要遍历全量，JOIN 持仓可能重复 code，记录按 code 去重。market_types 接受精确 subtype，不是 UI 粗分类。
- `apps/fund-select/src/lib/types.ts`：两个股基默认 3 年/5 亿/回撤 30/经理 5 年/夏普 0.8。lib/api.ts 做类型展开，原生 fetch 前缀为 /funds/api/funds。
- `apps/fund-select/src/components/FundsHeader.tsx`：导航与刷新耦合，FundsTab 同时用于 exportKind；应只提取公共导航，不能把第五 tab 当成刷新来源。
- `backend/fund-select/src/scheduler/scheduler.json`：股基两任务周六 08:05/10:05，Asia/Shanghai。manager 共享队列不包含普通刷新，不能在发布时从共享最新行猜测本轮结果。
- `backend/fund-select/src/db/session.py`：create_all 幂等建表，可新增独立历史表，无需重建旧表。
- `backend/fund-select/src/main.py`：通用 /{code} 详情路由在 router 内，新静态 /sharpe-board 应先注册。
- `apps/fund-select/src/app/api/funds/[...path]/route.ts`：GET/PATCH/POST 代理已有，无需新代理。Next basePath /funds；Link 无前缀，fetch 有前缀。
- `apps/fund-select/package.json`：无图表依赖；index-trends 已用 echarts ^6.0.0，可在 fund-select 独立安装同范围，不跨应用 import。
- `.trellis/spec/backend/fund-select/backend/contracts.md`：约束风险计算、单位、分页、市场分类和周任务。现有前端 lint 为 next lint、缺无交互配置，不能作为已通过的验证项。

数据边界：当前没有历史入选数据，不可恢复过去榜单；只记录入选者也无法知道缺席周夏普或未入选原因，不将本功能包装为风险稳定性评分。

工作区边界：本轮仅写本任务目录；已有 housing-price-freshness 任务改动不动。task.py create 自动带入了默认 douyin-processor package，需纠正为 fund-select，并在 metadata 记录前后端范围。
