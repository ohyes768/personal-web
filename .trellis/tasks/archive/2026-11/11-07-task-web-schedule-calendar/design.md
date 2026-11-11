# 设计：task-web 排期日历（月历总览 + 单日排期轴）

> 用户已确认方案 A（月历 + 单日轴主从布局）；B（周视图）与 C（纯月历格）被否决，周视图留作二期。

## 1. 页面结构

- 新路由 `/schedule`（basePath `/tasks` → 对外 `/tasks/schedule`）；`app/layout.tsx` 导航加「排期日历」。
- 主从布局：左月历固定宽 ~300px，右当日轴自适应；窄屏上下堆叠。
- 组件拆分（保持单文件聚焦）：
  - `app/schedule/page.tsx` — 状态与数据获取（月 summary、单日明细、URL 同步、轮询、过滤）；
  - `components/MonthCalendar.tsx` — 月历网格（纯展示 + onSelect 回调）；
  - `components/DayTimeline.tsx` — 单日轴（纯展示，点位 / 扎堆带 / 提示条）。

## 2. 数据契约（新增 2 个只读 API，不改表）

### 2.1 GET /api/schedule/summary?from=YYYY-MM-DD&to=YYYY-MM-DD

月历格数据。SQL（单查询，走现有 runs 数据）：

```sql
SELECT substr(COALESCE(scheduled_at, started_at, missed_schedule_at), 1, 10) AS d, status,
       COUNT(*) AS n,
       SUM(CASE WHEN status='interrupted' AND missed_schedule_at IS NOT NULL
                THEN 1 ELSE 0 END) AS missed
FROM runs
WHERE COALESCE(scheduled_at, started_at, missed_schedule_at) BETWEEN :from AND :to
GROUP BY d, status
```

Python 侧拼成：

```json
{"days": [{"date": "2026-11-07", "total": 11, "success": 9, "failed": 2,
           "timeout": 0, "missed": 0, "skipped": 0, "running": 0, "waiting": 0}]}
```

- **归日口径**：`COALESCE(scheduled_at, started_at, missed_schedule_at)` ——
  scheduled 触发按计划日、manual 按开始日、漏执行补记按 `missed_schedule_at`
  （补记行没有 started_at/scheduled_at，漏掉这一层整个补记都不会被聚合）；
- `missed` 只统计 `interrupted 且 missed_schedule_at 非空`，且 **`interrupted` 桶要扣除
  missed 部分**（补记行本身就是 interrupted 状态，不扣会重复计数）；
- 无记录的日期不返回行，前端按未来 / 空白处理。

### 2.2 GET /api/schedule/day?date=YYYY-MM-DD

单日轴数据。实现：

- 一次查询当天全部 runs：`COALESCE(started_at, scheduled_at) BETWEEN date 00:00:00 AND 23:59:59`，Python 按 `task_id` 分组；
- 对每个任务构造 `slots`，**槽来源规则**（关键）：
  - `date < today`：以 runs 记录为准 —— `trigger=scheduled` 的 `scheduled_at` ∪ `missed_schedule_at`（每条对应一个槽，槽状态取 run.status）；
  - `date > today`：以 `CronTrigger.from_crontab(cron, tz)` 推算全天触发时刻，全部为未来计划槽（仅 enabled 且 cron 合法的任务）；
  - `date == today`：≤ now 的时刻用 runs 规则，> now 的时刻用 cron 推算；
  - 手动 run（`trigger=manual`）不占计划槽，进 `manual` 列表。
- 响应：

```json
{"date": "2026-11-07", "tasks": [
  {"id": "index-trends-daily", "name": "指数趋势日更", "group": "script",
   "cron": "30 7 * * *", "enabled": true,
   "slots": [{"at": "2026-11-07T07:30:00", "kind": "run", "run": {"run_id": "...", "status": "success", "duration_ms": 12000, "trigger": "scheduled", "missed_schedule_at": null}},
             {"at": "2026-11-07T22:00:00", "kind": "planned"}],
   "manual": [{"at": "2026-11-07T15:12:00", "run": {"run_id": "...", "status": "success"}}]}
]}
```

- `kind`: `run`（有对应 run 记录）/ `planned`（未来计划）/ `pending`（已过时刻但暂无 run——漏执行检测每分钟 tick 补记前 ≤1 分钟的窗口，前端画虚线空心）。
- run 匹配复用 scheduler `_has_run_for_schedule` 同一规则：`run.trigger=="scheduled" and run.scheduled_at==fire` 或 `run.missed_schedule_at==fire`，**两侧都先过 `db.naive_local` 归一**（见 §9 时间戳口径）。
- 同一计划时刻多条记录只画一个槽（同刻去重）：真实 run 优先，修复前误补记的假漏执行行不会重复出点。
- `at > now` 的补记行一律忽略（未来不可能"漏执行"；修复前的枚举 bug 曾给未来触发点写过补记行）。
- `now` 作为 service 函数参数（默认 `datetime.now()`），测试可注入固定时间。

## 9. 时间戳口径（实现期发现，重要）

库内时间戳有两种来源：`db.now_str()` / executor 写入均为 **naive 本地串**（`2026-11-07T20:24:11`），
而 APScheduler 触发点 `isoformat()` **带时区后缀**（`2026-11-07T00:00:00+08:00`）。
修复前 `_detect_missed` 直接拿带后缀的串比较/落库，导致两类预存 bug（已修，均有回归测试）：

1. 与已执行 run 的 naive `scheduled_at` 永不相等 → 已执行时刻被补记成假漏执行；
2. 枚举无上界（`get_next_fire_time` 传 previous 后忽略 now）→ 未来触发点也被补记。

约定：**任何与库内时间戳的比较/落库，先过 `db.naive_local()` 归一**。
生产库中修复前写入的历史假补记行（`missed_schedule_at` 带后缀）仍在：
过去日期已被同刻去重隐藏；未来日期被 `at <= now` 过滤；runs 列表页仍会显示，
如需清理可在 NAS 上执行一次性 SQL（任务后续跟进，不属于本任务代码改动）。

## 3. 前端视觉语义

| 元素 | 样式 |
|---|---|
| 实心绿 `#16a34a` | 成功 |
| 实心红 `#dc2626` | 失败 |
| 实心紫 `#7c3aed` | 漏执行补记 |
| 实心蓝 `#2563eb` | 运行中 / 等待 |
| 空心灰 | 未来计划；`pending` 同为空心（更浅） |
| 蓝边方块 | 手动触发 |
| 红细竖线 | 现在（仅今天） |
| 琥珀竖带 + 提示条 | 扎堆（同一 HH:MM ≥2 任务） |

月历格底色优先级：failed/timeout → 红；missed → 紫；全 success/skipped → 绿；未来 → 灰；今天描边。

## 4. 轮询与状态

- 当日轴 5s、月 summary 30s（`setInterval`，与现有页面一致）。
- URL 同步：`/schedule?date=2026-11-07`，用 `router.replace` 更新（History 记录不过度膨胀）；无 `date` 默认今天。
- 过滤状态（group、只看异常）仅存组件 state，不入 URL。

## 5. 边界情况

- 禁用任务：保留行（任务名置灰），画历史槽、无未来计划槽。
- cron 非法：行尾灰字「cron 非法」，无未来计划槽。
- 新任务当月无 runs：只有未来空心点。
- 刚过触发点 ≤60s 无 run：`pending` 空心，等漏执行检测 tick 补记后变紫。
- 时间戳全部 naive 本地字符串；日期边界用字符串比较（与 `db.list_runs` 现状一致）。
- 月视图聚合不拉全量 runs（现有 `/runs` 有 500 上限，不适用）。

## 6. 兼容性

- 只新增路由与只读 API，不触碰现有 `/tasks`、`/runs`、`/runs/{run_id}` 与任何表结构。
- 前端复用 `lib/api.ts` 的 `Run` / `statusColor` / `statusLabel` 与 `globals.css` 现有类。

## 7. 测试设计（backend/task-web/tests/test_schedule_api.py）

- summary：多日多状态聚合；missed 与普通 interrupted 分开计数；from/to 边界含当天。
- day：过去日期（runs 为准 + 漏执行补记成槽）；未来日期（cron 枚举，disabled 任务无槽）；今天（now 分界拼接）；手动 run 进 manual；cron 非法任务无未来槽；now 注入固定时间。
- 环境遵循 `.trellis/spec/backend/testing-environment.md`（Windows basetemp 等约束）。

## 8. 回滚

无迁移、无 schema 变更：revert 提交即可完全回滚。
