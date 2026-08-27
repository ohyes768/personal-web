# Macro Scheduler Contract

> **Purpose**: macro 后端内建定时任务(APScheduler)的可执行契约。新增数据源接入调度、
> 改分组、排查定时任务问题时必读。来源:任务 08-26-macro-scheduler-page(2026-08-27),
> 架构复制自 `backend/dividend-select/src/scheduler/`(两处独立副本,改一处勿同步另一处)。
>
> **Last verified**: 2026-08-27
> **Source files**:
> - `backend/macro/src/scheduler/`(manager / jobs / routes / history / trading_calendar / cron_human)
> - `backend/macro/src/scheduler/scheduler.json`(任务预设,git 跟踪)
> - `backend/macro/src/main.py`(startup/shutdown 挂载)
> - 前端 `apps/macro/src/lib/modules/scheduler/`(types.ts 为本契约的 TS 镜像)

---

## 1. Scope / Trigger

- 新增/修改定时任务 API 签名、跨层 job/run 结构、APScheduler 基础设施集成时适用本契约。
- 模型:内建 AsyncIOScheduler(时区 Asia/Shanghai,单 worker),job 执行方式是
  **HTTP self-call** 到本地 update 端点(复用其锁与校验),不是函数直调。

## 2. Signatures

### 管理 API(挂载前缀 `/api`,前端经 rewrite 走 `/api/macro/scheduler/*`)

```
GET    /api/scheduler/jobs                    → {"jobs": SchedulerJob[]}
PATCH  /api/scheduler/jobs/{id}   body {"enabled": bool} → SchedulerJob
POST   /api/scheduler/jobs/{id}/run           → {"job_id": str, "triggered_at": iso}
GET    /api/scheduler/jobs/{id}/runs?limit=20 → {"job_id": str, "runs": SchedulerJobRun[], "total_returned": int}
```

### scheduler.json job 定义(`src/scheduler/scheduler.json`)

```json
{
  "id": "a_share_daily",
  "name": "A 股数据日度组",
  "target": "run_group",            // job 类型,固定值,映射到 jobs.JOB_TARGETS
  "cron": "10 16 * * 1-5",          // Asia/Shanghai,from_crontab 解析
  "enabled": true,
  "check_trading_day": true,        // true 时非 A 股交易日整组 skipped
  "targets": ["/update/china-bonds", "..."],  // 真正要跑的端点路径(有序,顺序执行)
  "description": "..."
}
```

## 3. Contracts

### SchedulerJob(列表项)

| 字段 | 类型 | 说明 |
|------|------|------|
| id / name / target / cron | str | 定义回显 |
| cron_human | str | cron 转中文,如"每周一至周五 16:10" |
| enabled | bool | 禁用时 `next_run_time` 为 null |
| next_run_time | iso+08:00 \| null | APScheduler 计算的下次触发 |
| last_run | SchedulerLastRun \| null | **仅** {start,end,status,count,reason,error},无 job_id/target/items(前端 `SchedulerLastRun = Pick<SchedulerJobRun,...>`) |
| description | str | |

### SchedulerJobRun(历史条目,JSONL 每次运行一条)

| 字段 | 类型 | 说明 |
|------|------|------|
| status | `success` \| `partial` \| `failed` \| `skipped` | 组内全部成功 / 有成有败 / 全败 / 非交易日 |
| count | int \| null | **成功的数据源个数**(非数据行数) |
| items | {path, status, count, ms, error}[] | 数据源级子明细,item.status 仅 success/failed |
| start / end | iso | |

### 成败判定(与 dividend 不同!)

macro 的 update 端点返回 **HTTP 200 + body `{success, message, data?}`**:
按 `body.success` 判定,`success:false` 记 failed 并存 message。**没有 409 特判**
(dividend 才有 already_running→skipped 语义)。

### 文件与环境

- 配置 `src/scheduler/scheduler.json`;运行历史 `data/scheduler/history.jsonl`;
  交易日历缓存 `data/scheduler/trading_calendar_cache.json`(TTL 30 天,拉取失败退旧缓存,再失败按交易日处理)
- self-call 端口 = `settings.service_port`;依赖 `apscheduler>=3.10,<4.0`

## 4. Validation & Error Matrix

| 条件 | 行为 |
|------|------|
| 未知 job_id | 404 `job not found: {id}` |
| scheduler 未初始化(app.state.scheduler 缺失) | 503 `scheduler 未初始化` |
| WEB_CONCURRENCY/UVICORN_WORKERS > 1 | 启动即 RuntimeError(单 worker 强制) |
| cron 表达式非法 | 该 job 跳过注册,error 日志,其余 job 正常 |
| scheduler.json 缺失 / jobs 为空 | 不注册任何任务 + error 大声报警(volume 覆盖坑) |
| 单源 self-call 异常/超时(httpx timeout=600) | 该源记 failed,**继续下一个** |
| check_trading_day 且非交易日 | 整组 `skipped`/`non_trading_day`,零请求 |

## 5. Good/Base/Bad Cases

- **Good**:`POST /jobs/a_share_daily/run` → 顺序跑 6 端点 → run 记 `status=success, count=6, items[6]`。
- **Base**:fund-flow 外部源断连 → 其余 5 源成功 → `status=partial, count=5`,items 内该源 `failed + error 原文`。
- **Bad**:`GET /jobs/unknown/runs` → 404;PATCH 不存在的 job → 404(不会静默创建)。

## 6. Tests Required

`backend/macro/tests/test_scheduler_*.py`(25 例,新增分组/端点后必须补):
- `test_scheduler_jobs.py`:run_group 四态聚合、单源失败不中断、URL 拼接契约、非交易日 skip(mock httpx 与 is_trading_day)
- `test_scheduler_history.py`:append/read_tail roundtrip(items 保留)、坏行跳过
- `test_scheduler_manager.py`:items 透传落盘、unhandled 异常落 failed
- cron 修改后:`test_scheduler_cron_human.py` 同步两个预设的中文断言

## 7. Wrong vs Correct

### Wrong:scheduler.json 放 `data/` 目录

```json
// ❌ data/ 在 .gitignore 且 docker-compose 用宿主机 ./data 覆盖 /app/data
// 新环境 clone → 0 任务;镜像 rebuild 也不含配置
```

### Correct:预设放代码目录,运行产物放 data/

```
src/scheduler/scheduler.json   # git 跟踪,随 COPY src/ 分发
data/scheduler/history.jsonl   # 运行历史(启停会写回前者的 enabled 字段)
```

### Wrong:给 macro 的 self-call 加 409→skipped 特判

```python
# ❌ 照抄 dividend jobs.py 的 interpret_409_as_skipped;macro update 端点不发 409
```

### Correct:按 body.success 判定

```python
data = resp.json()
item_status = "success" if resp.status_code == 200 and data.get("success") else "failed"
```

---

## Design Decisions

### 组任务(1 job = targets 列表)而非 1 job = 1 数据源

16 个数据源逐个建 job 配置与管理成本高;顺序执行天然限流外部 API。代价是 job 粒度
不能单独启停某个数据源——需要时把该源从 targets 拆出建独立 job 即可(架构支持)。

### 复制而非抽公共包

dividend 与 macro 独立部署,双方 scheduler 已有语义差异(409 判定、组任务、last_run 字段)。
两个消费者不构成抽象理由;复制是本仓库接受的惯例,漂移由本 spec 各自记录。

## How to Add a Data Source to Scheduling

1. 确认 `POST /api/update/<name>` 端点存在(macro 惯例:返回 UpdateResponse)
2. 按频率加入 `scheduler.json` 某组 `targets`(A 股类加 a_share_daily;全球类加 global_daily)
3. 若组是新频率,新增 job 定义(target 固定 run_group + cron + check_trading_day)
4. 跑 `pytest tests/test_scheduler_*.py -v`(改了预设 cron 要同步 cron_human 断言)
