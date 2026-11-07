# task-web 时间戳口径契约（naive 本地串）

> 来源：11-07-task-web-schedule-calendar 任务。日历视图暴露出两个预存 bug 的同一条根因。
> 适用：backend/task-web 一切涉及 `runs` 时间戳比较、聚合、落库的代码。

## 1. 契约

- 库内时间戳（`scheduled_at` / `started_at` / `finished_at` / `missed_schedule_at`）统一为
  **naive 本地串**（`2026-11-07T00:00:00`，Asia/Shanghai 单机，无时区后缀）。
- 唯一例外来源：APScheduler `CronTrigger.get_next_fire_time()` 返回 **aware datetime**，
  `isoformat()` 带后缀（`2026-11-07T00:00:00+08:00`）。
- **任何与库内时间戳的比较、聚合、落库之前，必须过 `db.naive_local()` 归一**。

## 2. Wrong vs Correct

```python
# Wrong：aware 串直接比较/落库——与库内 naive 串永不相等
fire_str = fire.isoformat(timespec="seconds")          # "...+08:00"
if run["scheduled_at"] == fire_str: ...                 # 永远 False
db.insert_run({..., "missed_schedule_at": fire_str})    # 写入带后缀串

# Correct
fire_str = db.naive_local(fire.isoformat(timespec="seconds"))
if run["scheduled_at"] == fire_str: ...
```

## 3. 已知踩坑（均已修，回归测试在 tests/test_schedule_api.py）

1. `_detect_missed` 用 aware 串落库/比较 → 已执行的时刻被补记成假漏执行；
2. `_detect_missed` 枚举无上界：`get_next_fire_time(previous, now)` 传 previous 后
   **忽略 now**，循环会把未来触发点也补记成漏执行——必须显式 `if nxt > now: break`；
3. `runs` 归日口径：`COALESCE(scheduled_at, started_at, missed_schedule_at)`——
   补记行没有 started_at/scheduled_at，漏掉第三层整个补记都不会被聚合；
4. `interrupted` 计数要扣除 missed（补记行本身是 interrupted 状态，不扣会重复计数）；
5. 历史脏数据：修复前写入的 aware 格式补记行仍在库中，视图侧用
   `db.naive_local` 归一 + 同刻去重 + `at <= now` 过滤兜底。

## 4. Quality Check

- [ ] 新增时间戳比较/落库是否全部经过 `db.naive_local`？
- [ ] 枚举 cron 触发点是否有 `<= now` 上界？
- [ ] 聚合/日视图是否考虑补记行（无 started_at/scheduled_at）？
