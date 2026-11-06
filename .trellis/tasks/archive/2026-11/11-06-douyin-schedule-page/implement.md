# 执行计划：douyin-processor 定时任务页面化

> 前置阅读：`prd.md` → `design.md` → `research/scheduler-pattern-survey.md`。
> 实现顺序按「后端可独立验证 → 前端 → 测试收尾」编排，每步有独立验证点。

## Phase A：后端 scheduler 包（可独立跑通）

- [ ] A1 移植通用件：`src/scheduler/{__init__,cron_human,history}.py`（自 `backend/dividend-select/src/scheduler/`），history 的 `build_record` 增加 `trigger` 字段（scheduled/manual）
      - 验证：`python -c "from src.scheduler.history import JSONLReaderWriter"`（venv 内）
- [ ] A2 `src/scheduler/jobs.py`：`_process_lock`（唯一锁源）+ `JOB_SPECS`（process_pending/cleanup_old_records，含 name/target/description）+ `JOB_TARGETS` 两个进程内目标；把 `main.py::_scheduled_cleanup` 逻辑迁入 `run_cleanup`，返回结构化结果（count=删除数）
      - 注意：`run_process_pending` 需先 `list_pending()` 判空（skipped/no_pending），再跑 `processor.process_pending()`，映射 failed→status
- [ ] A3 `src/scheduler/manager.py`：SchedulerManager
      - 构造参数：`(app_config: dict, data_dir: Path)`；crons 从 `app_config["process_pending"]` / `app_config["cleanup"]` 读取
      - `process_pending` job 挂 trigger 列表（两个 CronTrigger，timezone Asia/Shanghai 显式传）
      - enabled overlay：`data_dir/scheduler/enabled.json` 读写（tmp+os.replace 原子写）
      - `trigger_now(job_id, trigger="manual")` 用 DateTrigger + per-job lock；closing 时 raise RuntimeError
      - shutdown drain：pause admission → bounded asyncio.wait → shutdown(wait=False) → await EVENT_SCHEDULER_SHUTDOWN（spec 契约）
      - 单 worker 断言（沿 dividend）
- [ ] A4 `src/scheduler/routes.py`：4 个 API（GET /api/scheduler/jobs · PATCH /api/scheduler/jobs/{id} · POST /api/scheduler/jobs/{id}/run · GET /api/scheduler/jobs/{id}/runs），`_get_scheduler` 从 `request.app.state.scheduler` 取，未初始化 503
- [ ] A5 改造 `src/server/main.py`：lifespan 里删掉裸 add_job 块 → 构建 SchedulerManager（services={"processor": ...}）→ start → `app.state.scheduler`；启动时立即清理一次保留（调 jobs.run_cleanup 或保留原函数）；shutdown 走 manager.shutdown
- [ ] A6 改造 `src/server/endpoints.py`：`_process_lock` 改为从 `scheduler.jobs` import；`POST /api/process/pending` 在 manager 存在时委托 `trigger_now("process_pending")`（后台执行语义不变：立即返回 + 后台串行），manager 为 None 时回退旧路径
      - 验证：本地起服务 `python -m uvicorn src.server.main:app --port 8093`，curl 四个 API + 旧 /api/process/pending，观察 `data/scheduler/history.jsonl` 出现记录

## Phase B：测试（后端收尾门禁）

- [ ] B1 `pyproject.toml` dev-dependencies 加 pytest / pytest-asyncio（版本对齐其他服务）
- [ ] B2 `tests/test_scheduler_manager.py`：overlay 持久化/原子写、禁用不触发、trigger_now 互斥、history trigger 字段、双 cron trigger 构建、next_run_time 取最早
- [ ] B3 `tests/test_scheduler_routes.py`：4 API 的 200/404/503（TestClient 不起真调度线程，参照 task-web conftest 手法）
- [ ] B4 `tests/test_shutdown.py`：idle stop / 执行中 drain / closing 后拒绝手动触发
      - 验证：`cd backend/douyin-processor && uv sync --extra dev && uv run python -m pytest tests/ -v`

## Phase C：前端

- [ ] C1 `lib/types.ts`：SchedulerJob（id/name/crons/cron_human/next_run_time/enabled/last_run/description）+ SchedulerJobRun（trigger/start/end/status/count/reason/error）
- [ ] C2 `lib/api.ts`：schedulerApi（directClient：listJobs/setEnabled(PATCH)/runNow/getRuns）
- [ ] C3 代理 `app/api/douyin/[...path]/route.ts` 补 PATCH handler（照 POST 改造）
- [ ] C4 `components/SchedulerModal.tsx`：弹框 + 2 张 job 卡（cron 人话 / 下次触发 / 启停开关 / 立即执行 / 展开最近 20 条 runs，含 手动·定时 徽章）；样式沿 douyin paper/ink 体系，交互参照 `apps/dividend/src/components/SchedulerSettingsModal.tsx`
- [ ] C5 `app/page.tsx`：头部加齿轮按钮 + 挂弹框（RSS 按钮旁）
      - 验证：`cd apps/douyin && pnpm lint && pnpm build`；`pnpm dev` 后页面操作启停/立即执行/看历史（后端本地 8093）

## Phase D：收尾

- [ ] D1 全量验证：后端 pytest + 前端 lint/build + 本地手动冒烟（禁用 process_pending → 重启 → 确认不触发 → 重新启用）
- [ ] D2 `docker-compose.nas.yml` 核对：douyin-data 已挂 /app/data（enabled.json/history.jsonl 落卷），无需改 compose；确认无新端口/新卷
- [ ] D3 文档：`backend/douyin-processor/README.md` 增补「定时任务管理」一节（API 表 + 页面入口 + 历史文件位置）
- [ ] D4 spec 更新判断（Phase 3.3）：若 drain/overlay 实现踩坑，回写 `.trellis/spec/backend/douyin-processor/backend/`；douyin 若沿用 dividend spec 结论则在该 spec 加一行「douyin 同构复用」引用

## 风险与回滚点

| 风险 | 缓解 | 回滚 |
|---|---|---|
| trigger 列表 + from_crontab 时区偏移 | 每个 CronTrigger 显式 timezone=Asia/Shanghai；测试断言 next_run_time | revert A3 |
| _process_lock 迁移引 circular import | 锁放 scheduler/jobs.py，endpoints 单向 import；A6 完成即全量 import 检查 | revert A6 |
| 手动按钮语义变化 | /api/process/pending 响应结构不变（success/message/data.pending），前端零改动 | revert A6 |
| 代理 PATCH 遗漏 | C3 与 C2 同 commit；C5 冒烟必点启停 | revert C2/C3 |

## 审阅门（task.py start 前）

- [x] prd.md 收敛（含两项已决偏好）
- [x] design.md 定稿（含「2 卡 vs 3 卡」差异说明，待用户审阅确认）
- [x] implement.md 就绪
- [ ] 用户确认后 `task.py start 11-06-douyin-schedule-page`
