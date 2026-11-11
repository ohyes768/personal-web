# Implement — Hermes 跨 service 共享并发上限（2026-11-11 完成）

## 实施清单（对照 PRD）

- R1 共享限流器 ✅ `src/services/hermes_limiter.py`：BoundedSemaphore + active 计数，
  `from_env()` 工厂，过度释放防御。设计决策见 design.md D1（显式注入，非单例）。
- R2 接入点 ✅ 两 service `work()` 调度循环：pop 后 appendleft 放回队首，锁外
  `acquire(timeout=0.2)` 轮询等待；等待项保持 queued（可取消/调序）；拿到名额后
  持锁复核再标记 running；`_run_one` finally 释放。取消语义零变化。
- R3 配置语义 ✅ 无新增环境变量；`hermes_client.py` 的 `HERMES_MAX_CONCURRENT`
  注释更新为「quality + valuation 合计」。
- R4 测试 ✅ 新增 `tests/test_hermes_limiter.py`：
  - `test_quality_and_valuation_share_one_slot`：两类任务并行，max_seen == 1
  - `test_waiting_cancel_releases_no_slot_and_skips_submission`：等名额时取消，
    从未提交 Hermes，job cancelled=1，名额归零
  - `test_no_slot_leak_across_repeats`：3 只连跑，全部 succeeded、名额归零
  - 基础计数/下限保护 2 例
  顺手修复 `test_append_and_reorder_keep_one_waiting_order` 历史竞态（干净代码
  上套件内也 2/3 失败）：补 `_wait_until(000001 running)`。
- R5 契约文档 ✅ quality-rating-contract.md 新增 Cross-service cap 条目；
  valuation-contract.md submit 签名补 limiter 参数说明。

## 验收（对照 PRD Acceptance Criteria）

- [x] 并行时全局并发 ≤ HERMES_MAX_CONCURRENT（test_quality_and_valuation_share_one_slot）
- [x] 取消/调序/追加行为不变（既有 queue 控制用例全绿）
- [x] 全量 `pytest tests/ -q`：**435 passed, 3 skipped, 0 failed**（抖动测试已修复）
- [x] 无新增环境变量；注释已更新
- [x] 契约文档已更新

## 提交

- 后端+测试+文档：feat(dividend-select): Hermes 跨 service 共享并发上限
- 任务目录随代码一起提交
