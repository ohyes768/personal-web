# Hermes 跨 service 共享并发上限（quality / valuation 共用信号量）

## Goal

dividend-select 的基本面评级（quality）与四挡位估值（valuation）各自维护内存并发计数，
`HERMES_MAX_CONCURRENT` 名义"全局"实际各算各的：两类任务同时在跑时，对 Hermes 的实际并发是
2×limit。本任务引入**跨 service 共享的并发信号量**，让 `HERMES_MAX_CONCURRENT` 回归字面语义：
对 Hermes profile 的同时在跑 run 总数 ≤ limit。

## Background（确认事实，2026-11-11 复核）

- `quality_service.py` 与 `valuation_service.py` 的 `work()` 调度循环各自持有
  `_running` 计数与 `_pending` deque，`limit = max(1, hermes_config.max_concurrent)`，
  两个 service 互不感知（quality_service.py:334 / valuation_service.py:431 附近）。
- `refresh_jobs.py` 的 `RefreshJobManager` 执行器 `ThreadPoolExecutor(max_workers=2)`，
  因此 quality 与 valuation 两类 job 可以并行执行 → 两份 limit 同时生效。
- 两个 service 共用同一个 Hermes profile（`HERMES_PROFILE`，默认 ohyes768）与同一个
  Runs API 端点；上游若按 profile 限流，2×limit 会撞。
- 2026-11-11 已补齐 valuation 队列取消/调序（commit 822d9f8），取消语义依赖
  `_watch` 可中断轮询与提交前取消分支；并发控制改动不得破坏这些语义。

## Requirements

- **R1 共享限流器**：新建一个小对象（如 `src/services/hermes_limiter.py`），按
  `HERMES_MAX_CONCURRENT` 初始化 `threading.BoundedSemaphore`（模块级单例或由 main.py
  构造后注入两个 service；二选一在 design.md 定夺，倾向显式注入便于测试）。
  获取/释放必须覆盖「提交 run → 轮询到终态」整段；异常路径 `finally` 释放，不允许泄漏名额。
- **R2 接入点**：两个 service 在 `_execute`（或 `_run_one`）里、调用 `submit_run_fn`
  之前 acquire；取消语义保持：
  - 提交前已请求取消的项不 acquire、直接走 cancelled（现状行为不变）；
  - 等待信号量的项保持 `queued` 状态（不提前翻 `running`），被取消时能跳过；
  - 已在跑的项收到取消照旧走 `_watch` stop 流程。
  local `_running` 计数继续承担 job 终态判定，与共享信号量解耦。
- **R3 配置语义**：`HERMES_MAX_CONCURRENT` 文档/注释更新为「对 Hermes 的全局并发上限
  （quality + valuation 合计）」；`HermesConfig.max_concurrent` 仍是唯一来源，
  不新增环境变量。
- **R4 测试**：
  - 新增跨 service 用例：quality 与 valuation 同时各提交多只股票，观测同时处于
    "已提交未终态"的 run 总数 ≤ limit；
  - 信号量等待中取消：项能被取消且不占名额，job 记账正确（cancelled 计入）；
  - 信号量释放无泄漏：连续多轮提交后仍能跑满 limit；
  - 既有 `tests/test_quality_service.py`、`tests/test_valuation_service.py` 全绿
    （现有用例注入假的 submit/poll，需保证限流器可注入/可旁路，避免用例互相拖慢）。
- **R5 契约文档**：`.trellis/spec/backend/dividend-select/backend/quality-rating-contract.md`
  与 `valuation-contract.md` 补「共享并发上限」条目；`refresh-jobs-contract.md` 若提及
  executor 并发语义一并核对。

## Acceptance Criteria

- [ ] quality + valuation 并行时，同时在跑的 Hermes run 总数 ≤ `HERMES_MAX_CONCURRENT`
      （有测试证明）。
- [ ] 队列取消/调序/追加行为与 822d9f8 之后完全一致：取消等待项立即移出、运行项经
      stop 确认后才收尾、完成结果优先于取消请求。
- [ ] `cd backend/dividend-select && .venv/bin/python -m pytest tests/ -q` 全绿
      （test_quality_service 的 append/reorder 套件级抖动若复现，按已知问题记录，不算回归）。
- [ ] 无新增环境变量；`grep -rn "HERMES_MAX_CONCURRENT" backend/dividend-select/src` 语义注释已更新。
- [ ] 两份契约文档更新完毕。

## Out of Scope

- RefreshJobManager executor `max_workers=2` 的调整（两类 job 并行执行本身合理，
  只收敛对 Hermes 的并发）；
- hermes_trigger / task-web 侧的 Hermes 并发（它们单次单 run，不受影响）;
- 跨进程共享（本服务单进程部署，进程内信号量足够）；
- 估值/评级队列的功能性改动。

## Open Questions

（无。design.md 阶段再定：信号量是模块级单例还是 main.py 注入。）
