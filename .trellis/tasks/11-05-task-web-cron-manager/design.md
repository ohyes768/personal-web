# task-web 技术设计

基于 prd.md 已决策事项（方案 A 容器化、预登记制 + 密码手动执行、不补跑、先接 1 个任务）。

## 架构与边界

```
apps/task-web/          Next.js 前端（basePath /tasks，dev 端口 3011）
backend/task-web/       FastAPI 后端（端口 8101）
  src/
    scheduler.py        APScheduler 调度循环（独立于请求生命周期）
    executor.py         subprocess 执行器（进程组、超时、互斥、日志采集）
    models.py           SQLite 元数据 + 运行历史
    api/routes.py       REST API
  tasks.yaml            预登记任务清单（命令、工作目录、默认 cron、说明）
  data/                 SQLite + run 日志文件（named volume 挂载）
```

- 单一调度实例：APScheduler 在后端进程内运行，后端容器单副本（compose 无 scale）；不引入独立 worker。
- 部署进 `docker-compose.nas.yml`，bind mount `/home/ohyes768/stock-info-dingding`（只读意图由任务登记时声明，容器内以 `/workspace/stock-info-dingding` 访问）；时区 `Asia/Shanghai`。

## 数据模型（SQLite）

- `tasks`：id、name、description、command、cwd、default_cron、enabled、timeout_seconds、created/updated。
  实际运行配置存 `task_schedules`：task_id、cron 表达式、时区（第一版固定 Asia/Shanghai）、超时覆盖，使 Web 端"只改调度"有落点。
- `runs`：run_id、task_id、scheduled_at、started_at、finished_at、duration_ms、trigger(manual|scheduled)、status(waiting|running|success|failed|timeout|interrupted|skipped)、exit_code、missed_schedule_at（漏执行标记）。
- `runs` 不存 stdout/stderr 正文，日志写 `data/logs/<run_id>.out/.err`，`log_path` 入库；保留策略按天数清理，可配置（默认 30 天）。
- `scheduler_heartbeat`：调度心跳表（单行，updated_at），用于漏执行识别。

## 调度与执行

- APScheduler CronTrigger 按 task_schedules 注册；每次触发创建 run（status=waiting→running）。
- 互斥：同一 task 存在 running/waiting 时新触发记为 skipped（reason=mutex），手动与定时共用。
- 执行：`subprocess.Popen(cmd, cwd, start_new_session=True)`，stdout/stderr 追加写日志文件；超时 `os.killpg` 杀整个进程组，status=timeout。
- 手动执行 API 校验管理密码（`TASK_WEB_ADMIN_PASSWORD` 环境变量，沿用 skill-manager 模式）；不匹配返回 401。
- 漏执行识别：调度循环每分钟写心跳；对比"应执行时间"与实际 run 记录，缺失则补一条 status=interrupted、missed_schedule_at=应执行时间的记录（不补跑，仅留证）。不补跑策略落地方式。
- 重启恢复：启动时把所有 status=running 的旧 run 标记为 interrupted（第一版不做进程核验，写明局限）。
- 环境变量：任务登记可声明 env，但 API/页面只回显 key 不回显 value；日志脱敏由"不打印 env"保证。

## API（/api/task-web/*）

| 路由 | 说明 |
|------|------|
| GET /tasks | 任务列表（含上次执行、上次结果、下次计划时间） |
| PUT /tasks/{id}/schedule | 修改 cron/启停/超时 |
| POST /tasks/{id}/run | 手动执行（body 带 password） |
| GET /runs?task_id=&status=&from=&to= | 运行记录筛选 |
| GET /runs/{run_id} | 运行详情 |
| GET /runs/{run_id}/logs?tail= | 日志（支持轮询增量） |

## 前端（/tasks）

- 任务列表页：名称、cron、启停开关、上次结果徽章、下次计划时间、手动执行按钮（弹密码框）。
- 运行记录页：按任务/状态/时间筛选；详情页实时 tail 日志（3s 轮询，运行中），结束后展示全文与退出码。
- 结果含义提示：页面明示"退出码 0 = 进程正常退出，不代表业务投递成功"。

## 兼容与迁移

- 新增服务不影响现有 16 个服务；nginx 路由 `/tasks/*` → 3011、`/api/task-web/*` → 8101（沿 docker-compose.nas.yml 既有模式 + NAS 外部 Nginx）。
- A 股新股接入：任务登记 command 用 `bash run_a_stock.sh`（PUSH_MODE=1 已在脚本内）；导入默认 enabled=false，验证顺序：无外发测试任务 → dry-run → 用户确认后启用。

## 取舍与风险

- 依赖漂移：容器内 Python 依赖与宿主机不同 → 接入脚本时核对 import 并加入 task-web 镜像 requirements，写入 implement 验证步骤。
- 后端单进程同时承担 API 与调度：调度循环轻量（秒级 sleep），与现有后端模式一致；不做多副本。
- 第一版局限（明示不解决）：不做进程级重启核验、不做补跑、不做自动重试。

## 回滚

`docker compose -f docker-compose.nas.yml up -d --build` 不含 task-web 服务即可整体下线；named volume 保留运行历史可随时恢复。不动 NAS 上任何既有 cron/脚本。
