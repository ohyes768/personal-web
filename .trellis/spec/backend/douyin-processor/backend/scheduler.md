# Scheduler (douyin-processor)

> 内建定时调度管理模式。参照 `backend/dividend-select/src/scheduler/` 移植并适配 douyin。
> 生命周期契约（drain）与陷阱总纲见 `../../dividend-select/backend/scheduler-lifecycle.md`，douyin 同构遵循。

---

## Scenario: douyin 内建调度管理（页面化）

### 1. Scope / Trigger

- Trigger: 新增 4 个管理 API + 前端启停/立即执行/历史（跨层契约 + APScheduler 集成）
- 包结构固定：`src/scheduler/{manager,routes,jobs,history,cron_human}.py`，与 dividend/macro 同构
- 管理范围：全部定时任务（`process_pending` 09:45/17:15、`cleanup_old_records` 03:07）

### 2. Signatures

```python
# src/scheduler/manager.py
SchedulerManager(app_config: dict, data_dir: Path, services: dict)
  .start() -> None                        # 注册子 job 并启动；services 需含 processor + cleanup_days
  .shutdown(wait=True, timeout=30)        # drain 契约，lifespan yield 后 await
  .list_jobs() -> list[dict]              # 含 crons/cron_human/next_run_time/last_run
  .set_enabled(job_id, enabled) -> dict   # 立即生效 + 写 enabled.json overlay
  .trigger_now(job_id, trigger="manual")  # 同步；DateTrigger 立即跑；closing 时 RuntimeError
  .get_job_runs(job_id, limit=20) -> list

# src/scheduler/jobs.py —— target 统一签名（进程内直调，非 HTTP self-call）
target_fn(services: dict, job_id: str, trigger: str = "scheduled") -> dict
  # 返回 {"status": success|failed|skipped, "count":?, "reason"?, "error"?, "failed"?}

# src/server/endpoints.py —— 旧手动入口委托 manager，未初始化时回退 create_task
POST /api/process/pending  # 响应结构不变 {success, message, data.pending}
```

### 3. Contracts

- **API**（挂 `/api/scheduler`，经 nginx `/api/douyin/*` → 后端 8093）：
  - `GET  /api/scheduler/jobs` → `{jobs: SchedulerJob[]}`；SchedulerJob 含 `crons: string[]`、`cron_human`、`next_run_time|null`、`last_run| null`
  - `PATCH /api/scheduler/jobs/{id}` body `{enabled: bool}` → 更新后的 job；404 未知 id；503 scheduler 未启动
  - `POST /api/scheduler/jobs/{id}/run` → `{job_id, triggered_at}`；404/503 同上
  - `GET  /api/scheduler/jobs/{id}/runs?limit=1..200` → `{job_id, runs, total_returned}`；limit 越界 422
- **状态持久化分工**（与 dividend 的差异点）：
  - cron 来源 `config/app.yaml`（host 只读挂载，改后 restart 生效）
  - enabled 来源 `data/scheduler/enabled.json`（douyin-data 卷，tmp+os.replace 原子写，recreate 不丢）
  - 历史落 `data/scheduler/history.jsonl`（JSONL，5MB 滚动归档保留 3 份），schema 见 `history.build_record`（必含 `trigger: scheduled|manual|startup`）
- **锁**：`jobs._process_lock` 是唯一处理锁；cron、页面立即执行、旧手动入口三方共用；占锁时后到者记 `skipped/process_busy`（不等待）
- **多 cron 映射**：一个逻辑 job 多时刻 → APScheduler 子 job `{job_id}#{i}`（3.x `add_job` 不支持 trigger 列表）；启停 pause/resume 全部子 job；`next_run_time` 取最早
- **前端**：`schedulerApi`（lib/api.ts）走 `/api/douyin/scheduler/*`；Next 代理必须有 PATCH handler；本地 dev 需 `NEXT_PUBLIC_API_BASE_URL=/douyin`（basePath），生产走 nginx 不需要

### 4. Validation & Error Matrix

| 条件 | 行为 |
|---|---|
| `app.state.scheduler` 未初始化 | 管理 API 503；旧手动入口回退 create_task |
| 未知 job_id | 404 |
| manager closing / 未启动 | PATCH/run → RuntimeError → 503；wrapper 直接 return |
| cron 解析失败 | logger.error 跳过该子 job，其余照常注册 |
| `enabled.json` 损坏 | warn 后按全启用处理 |
| 撞 `_process_lock` | 记 `skipped/process_busy`，不重复消耗 ASR 配额 |
| pending 为空 | 记 `skipped/no_pending` |
| 多 worker（WEB_CONCURRENCY>1） | start() 直接 raise |

### 5. Good/Base/Bad Cases

- Good: 禁用 → enabled.json 写回 → 重启容器 → list_jobs.enabled=false 且子 job 全 paused（next_run_time=null）→ 启用恢复
- Base: 空锁空闲时手动触发 → DateTrigger 立即跑 → 历史 trigger=manual → UI 展开即见
- Bad: 在 start() 注册循环里用 `self._sched_sub_jobs()`（读 `self._scheduler`）做 pause——此时 `self._scheduler` 还是 None，pause 全部落空（见 §7）

### 6. Tests Required

`backend/douyin-processor/tests/`（pytest，同步外壳 + `asyncio.run(scenario())`）：

- `test_scheduler_manager.py`：overlay 写回与重启保持（断言 enabled.json 内容 + 重建后 enabled=false）、next_run_time 时区 `+08:00`、手动触发落历史（trigger=manual）、占锁 skipped、build_record schema、closing 拒绝 trigger_now
- `test_scheduler_routes.py`：stub manager 测 200/404/503/422；TestClient 不起真调度线程
- `test_scheduler_shutdown.py`：idle/drain 两模式（真 APScheduler + monkeypatch JOB_TARGETS）；断言 STATE_STOPPED、drain 等待在跑任务、closing 后拒绝新工作
- **AsyncIOScheduler 必须在运行中的事件循环内 start**（场景包在 `asyncio.run` 里）；同步上下文 start 会绑到无用 loop，shutdown 的 `EVENT_SCHEDULER_SHUTDOWN` 永不到达

### 7. Wrong vs Correct

#### Wrong —— start() 阶段 pause 子 job

```python
def start(self):
    scheduler = AsyncIOScheduler(...)
    scheduler.add_job(self._run_job_wrapper, trigger, id=f"{job_id}#{i}", ...)
    if not spec["enabled"]:
        self._pause_sub_jobs(scheduler, job_id)   # 内部读 self._scheduler → None → 落空
    scheduler.start()
    self._scheduler = scheduler
```

#### Correct —— helper 接受显式 scheduler 实例

```python
def _sched_sub_jobs(self, job_id: str, scheduler: AsyncIOScheduler | None = None) -> list:
    sched = scheduler if scheduler is not None else self._scheduler
    if sched is None:
        return []
    prefix = f"{job_id}#"
    return [j for j in sched.get_jobs() if j.id.startswith(prefix)]

def _pause_sub_jobs(self, scheduler, job_id):
    for sub in self._sched_sub_jobs(job_id, scheduler):
        scheduler.pause_job(sub.id)
```

#### Wrong —— 测试里同步上下文 start AsyncIOScheduler

```python
manager = make_manager(tmp_path)
manager.start()                 # 无 running loop → 绑到未驱动的 loop
asyncio.run(manager.shutdown()) # EVENT_SCHEDULER_SHUTDOWN 永不到达
```

#### Correct

```python
async def scenario():
    manager = make_manager(tmp_path)
    manager.start()             # AsyncIOScheduler 捕获 running loop
    ...
    await manager.shutdown()
asyncio.run(scenario())
```

---

## Gotchas

> **Warning**: APScheduler 3.x 的 `CronTrigger.from_crontab` 不传 `timezone` 会落到系统时区（容器 UTC），触发时间偏移 8 小时。scheduler 与每个 trigger 必须显式共用 `Asia/Shanghai`；dow 数字 0=周一（不是 crontab 的周日），工作日写 `mon-fri`。

> **Warning**: `pause_job` 本质是 `modify_job(next_run_time=None)`；对 pending job 在 `scheduler.start()` 之前调用时，`_real_add_job` 因 `hasattr(job, 'next_run_time')` 为真而跳过重算——所以启动期 pause 是生效的，前提是真的调到了（见 §7）。
