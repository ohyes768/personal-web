# 技术设计：douyin-processor 定时任务页面化

> 参照 `research/scheduler-pattern-survey.md`。总体策略：移植 dividend/macro 的 `src/scheduler/` 包模式，按 douyin 实际（进程内目标、app.yaml cron 源、douyin-data 卷）做适配。

## 1. 架构与边界

```
backend/douyin-processor/
├── src/
│   ├── scheduler/                    # 新增包
│   │   ├── __init__.py
│   │   ├── manager.py                # SchedulerManager（移植 dividend，简化）
│   │   ├── routes.py                 # /api/scheduler/* 4 个管理 API
│   │   ├── history.py                # JSONLReaderWriter + build_record（移植，加 trigger 字段）
│   │   ├── jobs.py                   # JOB_TARGETS：进程内直调 + 共享 _process_lock
│   │   └── cron_human.py             # 移植 dividend（通用工具）
│   ├── server/
│   │   ├── main.py                   # lifespan 改造：裸 add_job → SchedulerManager
│   │   └── endpoints.py              # /api/process/pending 委托 manager；锁迁移
│   └── processor/                    # 不动（video_processor/status_manager 原样）
├── tests/                            # 新增（pytest）
└── config/app.yaml                   # 不动（cron 源不变）

apps/douyin/src/
├── components/SchedulerModal.tsx     # 新增弹框（参照 dividend SchedulerSettingsModal）
├── lib/api.ts                        # +schedulerApi
├── lib/types.ts                      # +SchedulerJob/SchedulerJobRun 类型
└── app/
    ├── page.tsx                      # 头部加齿轮入口 + 挂弹框
    └── api/douyin/[...path]/route.ts # +PATCH handler
```

边界：不动转写/清理业务逻辑本身；不动 task-web；不动 n8n 相关网络拓扑。

## 2. SchedulerManager 设计（与 dividend 的差异点）

### 2.1 数据来源三件套

| 数据 | 来源 | 理由 |
|---|---|---|
| job 定义（id/name/target/description） | `jobs.py` 内 `JOB_SPECS`（代码注册表） | douyin 只有 2 个 job、无 per-job 参数，不值得 JSON 文件 |
| cron | `config/app.yaml` 现有 `app.process_pending.cron_morning/cron_evening`、`app.cleanup.cron` | 延续现有「host 改文件 + restart」运维习惯；ro 挂载 recreate 不丢 |
| enabled 状态 | `data/scheduler/enabled.json`（douyin-data 卷）overlay | `{"process_pending": true, "cleanup_old_records": true}`；写回用 tmp+os.replace 原子写；recreate/rebuild 都不丢 |

> 与 dividend 的差异记录：dividend 把 cron+enabled 都放镜像内 scheduler.json 写回（writable layer，recreate 丢 enabled）。
> douyin 拆成「cron 走 app.yaml、enabled 走 data 卷」，两者均持久，且不改变现有 cron 修改流程。

### 2.2 Job 清单（2 个逻辑 job）

| id | target | crons（app.yaml） | 说明 |
|---|---|---|---|
| `process_pending` | `process_pending` | `45 9 * * *` + `15 17 * * *` | 一个 job 挂**两个 CronTrigger**（APScheduler 3.x add_job 支持 trigger 列表）；UI 显示「每天 09:45 / 17:15」 |
| `cleanup_old_records` | `cleanup` | `7 3 * * *` | 清理 45 天前记录 |

> 注意：prd 阶段用户选了「3 个任务全管」，本设计把 09:45/17:15 合并为一个逻辑 job（两个触发时刻同卡显示），
> 管理能力不减（启停 = 两个时刻一起停；立即执行 = 同一 target；历史同卡）。若审阅时要恢复 3 卡形态，
> 改回 scheduler 侧两个 job id 即可（实现成本几乎相同），在审阅时确认。

`next_run_time` 取 trigger 列表的最早下次触发。

### 2.3 生命周期（沿 scheduler-lifecycle spec）

- `start(services)`：`services = {"processor": video_processor}`；从 JOB_SPECS + app.yaml 组装 trigger；enabled=false 的 job 不注册（或注册后 pause）；`job_defaults={max_instances:1, coalesce:True, misfire_grace_time:3600}`
- `shutdown(wait=True, timeout=30)`：pause admission → 拒绝新 trigger_now → `asyncio.wait` 有界 drain → `shutdown(wait=False)` → await `EVENT_SCHEDULER_SHUTDOWN`（spec 契约，先例 `dividend-select/tests/test_scheduler_shutdown.py`）
- 无 self-call 端口探活（douyin 目标是进程内直调，探活无意义）
- 单 worker 断言保留（容器本就单进程，防御性）

### 2.4 jobs.py 目标实现（进程内直调，区别于 dividend 的 self-call）

```python
# src/scheduler/jobs.py
_process_lock = asyncio.Lock()   # 唯一锁源，endpoints 与 cron 共用

async def run_process_pending(ctx, job_id, trigger) -> dict:
    async with _process_lock:
        pending = await ctx.services["processor"].status_manager.list_pending()
        if not pending:
            return {"status": "skipped", "reason": "no_pending", "count": 0}
        result = await ctx.services["processor"].process_pending()
        status = "success" if result.get("failed", 0) == 0 else "failed"
        return {"status": status, "count": result.get("completed"), "failed": result.get("failed")}

async def run_cleanup(ctx, job_id, trigger) -> dict:
    # 复用现 main._scheduled_cleanup 逻辑（迁移到本文件），返回 {"status","count":删除数,"failed":[...]}
```

历史记录 schema（history.py `build_record` 扩展）：

```json
{"job_id": "process_pending", "target": "process_pending", "trigger": "scheduled|manual",
 "start": "...", "end": "...", "status": "success|failed|skipped", "count": 3, "reason": "...", "error": "..."}
```

## 3. API 契约（挂 `/api/scheduler`，与现有 endpoints 全路径风格一致）

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/scheduler/jobs` | `{jobs:[{id,name,crons,cron_human,next_run_time,enabled,last_run,description}]}` |
| PATCH | `/api/scheduler/jobs/{id}` | body `{enabled:bool}`；写 enabled.json overlay；立即生效（注册/pause）；404/503 语义同 dividend |
| POST | `/api/scheduler/jobs/{id}/run` | DateTrigger 立即跑；返回 `{job_id, triggered_at}`；scheduler closing 时 503 |
| GET | `/api/scheduler/jobs/{id}/runs?limit=20` | 尾读 JSONL，最新在前 |

兼容：`POST /api/process/pending` 保留，内部改为 `manager.trigger_now("process_pending")`（trigger=manual）；
manager 未初始化时回退旧直调路径（防启动窗口 500）。前端「待处理(N)」按钮零改动。

## 4. 前端设计

- `SchedulerModal.tsx`：弹框（douyin paper/ink 设计语言）；2 张 job 卡：名称 + cron 人话 + 下次触发 + 启用开关 + 立即执行 + 可展开最近 20 条 runs（状态徽章 / 耗时 / count / reason / 手动·定时标记）；沿用 dividend modal 的交互（打开拉 jobs，展开卡片拉 runs，操作后局部刷新）
- `lib/types.ts`：`SchedulerJob` / `SchedulerJobRun`（含 trigger 字段）
- `lib/api.ts`：`schedulerApi = { listJobs, setEnabled, runNow, getRuns }`（directClient）
- 代理 `route.ts`：补 `PATCH` handler（GET/POST/DELETE 已有）
- 入口：page.tsx 头部 RSS 左/右侧加齿轮图标按钮（title=定时任务管理）

## 5. 测试设计（从零起步）

pyproject dev-dependencies 加 `pytest`、`pytest-asyncio`（版本与仓库其他服务对齐）。

| 测试文件 | 覆盖 |
|---|---|
| `tests/test_scheduler_manager.py` | enabled overlay 加载/写回/原子性；禁用 job 不触发；trigger_now 互斥（cron 手动撞锁）；history 记录 trigger 字段；crons 列表 → trigger 构建 |
| `tests/test_scheduler_routes.py` | 4 个 API 200/404/503 语义（TestClient，参照 task-web conftest 的「不启动真调度线程」手法） |
| `tests/test_shutdown.py` | drain 契约：idle stop / 执行中 drain / 关闭后拒绝手动触发（沿 dividend spec 清单裁剪） |

## 6. 兼容与回滚

- 兼容：cron 行为/时间不变；`/api/process/pending`、RSS、前端列表全部不变；status.json 结构不变
- 回滚：单 commit 粒度 revert + 重启容器即回旧形态；无数据迁移（enabled.json/history.jsonl 是新增文件，删掉无副作用）

## 7. 运维影响

- 改 cron：仍改 `config/app.yaml` + `docker restart douyin-backend`（与今天一致）
- 启停：页面操作，立即生效且持久（douyin-data 卷）
- 查历史：页面（最近 20 条）或 `douyin-data:/app/data/scheduler/history.jsonl`（5MB 滚动归档，保留 3 份）
