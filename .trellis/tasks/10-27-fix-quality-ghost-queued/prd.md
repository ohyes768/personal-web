# 股息率评级任务互斥与幽灵 queued 修复

## Goal

修复 `QualityService.submit_analysis` 在已有 active quality job 时重复提交造成的
状态污染：幽灵 `queued` 残留 + 正在运行 job 的 per_code 实时状态被误清。
让"排队"状态只可能由真正开跑的 job 写入。

## 背景与根因

`backend/dividend-select/src/services/quality_service.py` L230-233 在
`refresh_jobs.submit()` 之前同步执行 `_per_code.clear()` + 全批写 `queued`；
而 `RefreshJobManager.submit()`（`src/services/refresh_jobs.py` L80-82）只要存在
active（queued/running）同 kind job 就直接 `return existing`（reused），新的
`work()` 永远不执行。后果：

| 受影响条目 | 表现 |
|---|---|
| 旧 job 已完成的 code | 状态被 clear 后无人回写（run_one 仅在该股结束时写一次）→ 前端行状态永久消失 |
| 旧 job 进行中的 code | 短暂消失，跑完回写，中间显示错乱 |
| 新提交且不重叠的 code | 幽灵 queued，永不更新 |

现测试 `test_active_job_reused`（tests/test_quality_service.py L221）只断言
reused 标志，未覆盖 per_code 残留，因此 bug 未被拦截。

## Requirements

1. **提交互斥**：`submit_analysis` 在写入任何状态前先检查
   `refresh_jobs.active("quality")`：
   - 无 active job → 正常受理；
   - 有 active job 且其 `codes` **完全包含**本次请求 codes → 保持现有 reused
     语义（幂等重交，返回该 job，不写任何 per_code 状态）；
   - 有 active job 且本次请求存在其 codes 之外的股票 → `raise ValueError`
     （routes.py L3634 已有 ValueError→400 映射，前端自动展示提示文案）。
2. **状态写入时机**：`_per_code` 的清批 + 逐股写 `queued` 从 `submit_analysis`
   主体挪进 `work()` 内部开头——只有 job 真正被接受并开跑后才写状态，reused
   路径永远不触碰 per_code。
3. **清除范围收窄**：work() 内只清除**本次 codes** 的 per_code 条目并重写
   queued，不再 `_per_code.clear()` 全表清（避免误伤并行 job 的 running 状态）。
4. **测试补充**（tests/test_quality_service.py）：
   - active job 期间提交包含新 code 的请求 → `pytest.raises(ValueError)`，
     且 active job 的 per_code 状态未被改动；
   - codes 完全包含于 active job 时 reused → 返回同 job_id / reused=True，
     且 per_code 中不残留多余 queued 条目。

## 约束

- 不改 `RefreshJobManager` 通用逻辑（m120/financial 共用它，reused 语义保持）；
- 不改 API 契约：`POST /quality/analyze` 仍 202 + job dict，新增失败路径走
  已有 400 映射；
- 单进程内存态（服务重启即清空）语义不变，不引入持久化。

## Acceptance Criteria

- [x] active quality job 运行中，提交含新 code 的批量请求 → ValueError（HTTP 400），错误文案含"已有评级任务在跑"类提示；
- [x] reused 路径（codes 完全被包含）不写 per_code，无幽灵 queued；
- [x] 正常路径：job 受理后 per_code 逐股 queued → running → completed/failed 与现行为一致；
- [x] 新增 2 条测试 + 既有 quality 测试全部通过：`python -m pytest tests/test_quality_service.py -v`（backend/dividend-select 下）；
- [x] `python -m pytest tests/ -q` 全量回归无新增失败。

## Notes

- 提交互斥的判断放在 `submit_analysis` 内部而非 routes.py：服务层已持有
  `refresh_jobs` 引用，且测试可直接在服务层覆盖，无需构造 HTTP 层。
- work() 开头写 queued 与 run_one 的 running 之间存在极小窗口，前端为轮询
  展示，无感知，可接受。
