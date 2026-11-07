# 实现计划：task-web 排期日历

> 复杂任务：prd.md + design.md + implement.md 齐备后 `task.py start`。
> 设计要点见 design.md；本文只列执行顺序、验证命令与回滚点。

## 执行清单（按序）

### 后端 backend/task-web

- [x] 1. `src/schedule.py`（新文件，纯函数服务层）：
  - `summary_days(from_str, to_str) -> list[dict]`（SQL 聚合，见 design 2.1）；
  - `day_view(date_str, now=None) -> dict`（runs 分组 + CronTrigger 枚举 + 槽来源规则，见 design 2.2）。
  - 复用 `db.get_conn` / `db.list_tasks`，不复制 SQL 风格。
- [x] 2. `src/api/routes.py` 挂载：
  - `GET /schedule/summary?from=&to=`（校验 from ≤ to，格式 YYYY-MM-DD）；
  - `GET /schedule/day?date=`。
- [x] 3. 测试 `tests/test_schedule_api.py`（TDD：先写测试再补实现）：
  - 覆盖 design §7 全部用例；临时库参照现有 tests 的 fixture 写法。

### 前端 apps/task-web

- [x] 4. `lib/api.ts`：新增 `ScheduleSummary` / `ScheduleDay` / `Slot` 类型与 apiGet 复用。
- [x] 5. `components/MonthCalendar.tsx`：月历网格（周一起始、chips、底色优先级、切月回调）。
- [x] 6. `components/DayTimeline.tsx`：单日轴（行、点位、now 线、扎堆带与提示条、hover/点击）。
- [x] 7. `app/schedule/page.tsx`：URL `?date=` 同步、轮询（5s/30s）、group + 只看异常过滤、组装左右布局。
- [x] 8. `app/layout.tsx`：导航加「排期日历」。

### 计划外发现（已修复，均有回归测试）

- [x] 9. 调度器 `_detect_missed`：`missed_schedule_at` 原为带时区 ISO 串，与库内 naive 串永不相等 →
  已执行的时刻被补记成假漏执行；统一 `db.naive_local` 归一（scheduler + schedule 视图两侧）。
- [x] 10. 调度器 `_detect_missed`：枚举无上界（`get_next_fire_time` 传 previous 后忽略 now）→
  未来触发点也被补记成漏执行；加 `nxt > now` 即停；日视图对 `at > now` 的补记行过滤兜底。
- [x] 11. `next.config.mjs`：standalone trace 拷贝在 Windows 无 symlink 特权时 EPERM；
  加 `TASK_WEB_NO_STANDALONE=1` 开关（部署不变）。

## 验证命令

```bash
# 后端测试（Windows 遵循 .trellis/spec/backend/testing-environment.md）
cd backend/task-web && uv run python -m pytest tests/ -v

# 前端
cd apps/task-web && pnpm build && pnpm lint
```

- 手动验收：打开 `/tasks/schedule`（dev 3011），对照 prd.md Acceptance Criteria 逐条勾选。

## 审查关口

- 实现完成后跑 `trellis-check`（skill）做全量核查（lint/测试/跨层一致性）。
- Phase 3.3 评估是否沉淀 spec（如「task-web 新增只读 API 约定」），无则记录判断结论。

## 回滚点

- 每 commit 一批可独立 revert；无 schema / 迁移，回滚即恢复原状。
- 若前端构建失败阻塞，先 revert `apps/task-web` 提交，后端 API 无副作用可保留。
