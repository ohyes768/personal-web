# Scheduler Pattern Survey（仓库内定时任务管理形态调研）

> 2026-11-06 取证。目的：为 douyin-processor 的「定时任务页面化」选定参照模式。

## 结论先行

dividend-select 与 macro 是**同一套**内建调度管理模式（`src/scheduler/` 包结构逐文件同构），
fund-select 是其轻量变体，task-web 是另一条（命令型预登记制）路线。douyin 应照 dividend/macro 模式做进程内移植。

## 1. dividend-select（最完整先例，且同样经历了 n8n → 内建的迁移）

后端 `backend/dividend-select/src/scheduler/`：

| 文件 | 职责 |
|---|---|
| `manager.py` | `SchedulerManager`：AsyncIOScheduler + MemoryJobStore；job 定义来自 `scheduler.json`（id/name/cron/enabled/target）；`set_enabled` 写回 JSON 配置；`trigger_now` 用 DateTrigger 一次性任务；per-job asyncio.Lock 防重入；单 worker 断言（WEB_CONCURRENCY/UVICORN_WORKERS）；shutdown drain（pause admission → bounded asyncio.wait → shutdown(wait=False) → await EVENT_SCHEDULER_SHUTDOWN）；延迟端口探活（self-call 场景专用） |
| `routes.py` | 4 个管理 API（prefix `/scheduler`，最终 `/api/dividend/scheduler/*`）：`GET /jobs` · `PATCH /jobs/{id}`（enabled）· `POST /jobs/{id}/run` · `GET /jobs/{id}/runs?limit=20` |
| `history.py` | `JSONLReaderWriter`：追加写（asyncio.Lock 串行）+ 尾部倒读 + 5MB 滚动归档（保留 3 份）；`build_record` 固定 schema |
| `jobs.py` | `JOB_TARGETS` 注册表；target 通过 **HTTP self-call** 打本地 `/api/dividend/*`（因为 job 需要过完整 API 层） |
| `cron_human.py` | cron → 人话（「每天 09:45」）；注意 APScheduler 3.x dow 数字 0=周一陷阱 |
| `scheduler.json` | `{version, jobs:[{id,name,target,cron,enabled,check_trading_day,params,description}]}`；**放在 `src/scheduler/` 下随镜像走**，注释明确：避开 /app/config 的 NAS named volume 覆盖（启停要写回，不能放被覆盖的挂载点） |

关键先例决策（`apps/dividend/src/components/SchedulerSettingsModal.tsx:178` 注释原文）：
「替代外部 n8n 定时触发。**cron 由配置文件固定，UI 仅开放启用/禁用与立即执行**」——UI 不做 cron 编辑。

时区陷阱（manager.py:22-28 注释）：`from_crontab` 不传 timezone 会落到系统时区（容器 UTC）→ 触发时间偏移 8 小时。scheduler 与每个 trigger 必须共用 Asia/Shanghai。

前端 `apps/dividend/src/components/SchedulerSettingsModal.tsx`：主页弹框；job 卡片（cron 人话、下次触发、启停开关、立即执行）+ 每卡最近 20 条 runs（状态徽章、耗时、count/reason）。数据源 `schedulerApi`（listJobs/getRuns/setEnabled/runNow）。

spec：`.trellis/spec/backend/dividend-select/backend/scheduler-lifecycle.md` —— shutdown drain 契约 + 回归测试清单（`tests/test_scheduler_shutdown.py`）。

## 2. macro（同构 + 独立页面变体）

- `backend/macro/src/main.py:42-64`：SchedulerManager(config_path=src/scheduler/scheduler.json[git 跟踪], history=data/scheduler/history.jsonl)
- `backend/macro/src/scheduler/routes.py`：同样 4 个 API，prefix `/api/scheduler/*`
- 前端 `apps/macro/src/app/modules/scheduler/`：独立路由页 `/macro/scheduler`（JobCard / RunsHistory / ItemTable 三组件），入口是悬浮齿轮
- 页面 footer 注明历史文件位置 `data/scheduler/history.jsonl` 与日志 `logs/scheduler.log`

## 3. fund-select（轻量变体）

- `backend/fund-select/src/scheduler/manager.py`：同构 SchedulerManager（4 API 同形）
- 前端 `apps/fund-select/src/components/SchedulerDialog.tsx`：`<dialog>` 弹框，`?scheduler=1` 可直达

## 4. task-web（不采用）

`backend/task-web/`：预登记制通用调度台（tasks.yaml 唯一任务来源，Web 只能改 cron/启停），runs 表 + 日志文件 + 心跳。
适合 shell/docker 命令型任务（当前仅 demo-* 与 a-stock-push）。douyin 的调度是进程内组件调用，
套 task-web 需要把逻辑拆成命令行并新增登记，与其他服务形态不一致 → 不走。

## 5. douyin-processor 现状（被改造方）

- 调度：`src/server/main.py:140-176` lifespan 内裸 `AsyncIOScheduler`，3 个 job（process_pending_morning 45 9 * * * / process_pending_evening 15 17 * * * / cleanup_old_records 7 3 * * *），无管理 API、无历史
- cron 配置：`config/app.yaml` `app.process_pending.cron_morning/cron_evening`、`app.cleanup.cron`（**host 只读挂载**，改后 restart 生效，recreate 不丢）
- 手动入口：`src/server/endpoints.py:28,169-212` POST `/api/process/pending`，与定时共用模块级 `_process_lock`
- 清理逻辑：`main.py:28-58 _scheduled_cleanup`（status_manager.cleanup_old_records + 删 wav + 删 output json）
- `processor.process_pending()`（`src/processor/video_processor.py:42-140`）返回 {total, completed, failed, ...} 类汇总
- 测试：**无 tests/ 目录**，pyproject dev-dependencies 为空
- 部署：`docker-compose.nas.yml:128-150` douyin-backend（douyin-data→/app/data、douyin-logs→/app/logs、config ro 挂载）

## 6. 前端链路细节

- Next 代理 `apps/douyin/src/app/api/douyin/[...path]/route.ts`：只有 GET/POST/DELETE handler，**无 PATCH** —— 启停 API 若用 PATCH 需补代理 handler
- `lib/api-client.ts`：wrapped/direct 双模式；douyin 现有代码多用 directClient（后端返回裸 JSON）
- 页面：`apps/douyin/src/app/page.tsx` 单页，头部已有 RSS 订阅 + 待处理按钮，弹框入口可加在此处

## 7. 设计启示（转入 design.md 的输入）

1. manager/routes/history/cron_human 可从 dividend 移植；jobs.py 不用 self-call（douyin 目标就在同进程），直接函数调用 + 复用 `_process_lock`
2. cron 保留在 app.yaml（延续现有「改文件 + restart」运维习惯，且 ro 挂载 recreate 不丢）；enabled 状态 + history 放 douyin-data 卷（`data/scheduler/`），recreate/rebuild 都不丢 —— 比 dividend 的「写回镜像层配置」更稳，差异在 design.md 记录理由
3. UI 沿 dividend 决策：不编辑 cron，只启停 + 立即执行 + 看历史
4. 前端弹框形态（用户已选）；代理补 PATCH
5. 测试从零起步：加 pytest dev 依赖 + tests/，重点覆盖启停持久化、互斥、历史 schema、cron 时区
