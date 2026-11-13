# Design — Hermes 跨 service 共享并发上限

## 决策记录（2026-11-11）

### D1 信号量形状：显式注入，不做模块级单例

`HermesLimiter`（`src/services/hermes_limiter.py`）由 `main.py` 构造一次
（`HermesLimiter.from_env()`，读 `HERMES_MAX_CONCURRENT`），通过
`QualityService(path, limiter=)` / `ValuationService(path, limiter=)` 注入两个 service。

- `limiter=None`（默认）= 不参与全局限流，本地 `HERMES_MAX_CONCURRENT` 照旧生效。
  现有测试零改动、零拖慢（不用共享实例互相排队）。
- 内部是 `threading.BoundedSemaphore` + 活跃计数（`active`，供测试断言）；
  `release()` 对过度释放做防御（忽略而非抛错，避免异常路径把进程搞崩）。
- 单进程部署，进程内信号量足够；PRD Out of Scope 已排除跨进程。

### D2 接入点：调度线程在锁外等名额，等待项保持 queued

调度循环改造（quality / valuation 同构）：

1. 本地名额判定照旧（`_running >= limit` 用 `_cond.wait()`）。
2. 队首 pop 后若有效，**appendleft 放回队首**，在 `_cond` 锁外等全局名额
   （`limiter.acquire(timeout=0.2)` 轮询，不长期持锁）。
3. 等待期间项仍是 `queued` 且在 `_pending` 里 → **取消/调序语义完全不变**
   （cancel_item 只对 `code in self._pending` 的 queued 项生效）。
4. 拿到名额后持锁复核（仍 queued 且在队列）→ `remove(code)` 出队 → 标记
   `running` → `_running += 1` → 起 `_run_one` 线程，`holds_slot=True`。
5. 复核失败（等待中被取消/移除）→ 已拿到的名额立即 release → 回调度循环。
6. `_run_one` 整体包 `try/finally`，`finally` 里 `limiter.release()`——
   提交/轮询/落盘任何异常路径都归还名额，不泄漏。

本地 `_running` 计数继续承担 job 终态判定（空队列 + 无在跑 → 收尾），
与全局闸解耦；单任务行为与改造前一致（全局 limit 通常等于本地 limit）。

### D3 已知权衡

- 名额释放后调度线程靠 `acquire(timeout=0.2)` 轮询唤醒，最多 200ms 延迟——
  相对 Hermes run 的分钟级耗时可忽略。
- BoundedSemaphore 无 FIFO 公平性；排队顺序仍由本地 `_pending` 队列保证，
  信号量只决定"何时放行队首"。
- `HERMES_MAX_CONCURRENT` 语义收窄为「对 Hermes 的全局并发上限（两类合计）」，
  已在 `hermes_client.py` 配置注释与两份契约文档写明；无新增环境变量。

## 修改文件

- 新增 `src/services/hermes_limiter.py`
- `src/services/quality_service.py` / `valuation_service.py`：`__init__` 注入、
  `work()` 调度循环、`_run_one` finally 释放
- `src/main.py`：构造共享实例注入两个 service
- `src/services/hermes_client.py`：`HERMES_MAX_CONCURRENT` 注释更新
- 测试：新增 `tests/test_hermes_limiter.py`（5 用例）；
  修复 `test_quality_service.py::test_append_and_reorder_keep_one_waiting_order`
  的历史竞态（front() 抢在 000001 标记 running 之前执行，加 `_wait_until(000001 running)`）
