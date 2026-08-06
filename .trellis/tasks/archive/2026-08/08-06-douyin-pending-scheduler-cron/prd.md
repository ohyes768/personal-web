# douyin-pending-scheduler-cron

## Goal

把 ASR pending 处理从「外部触发（n8n + 前端手动按钮）」改为「后端 APScheduler 自调度」。
每天 09:45 和 17:15 北京时间，自动调用既有的 `process_pending` 流程，处理 status=pending 的视频。

降低对 n8n 等外部服务的依赖，n8n 后续可停掉对应 webhook。

## Background

- 用户原有两个触发点：
  1. **前端手动按钮**（保留作为应急通道，本任务不动）
  2. **n8n 外部定时触发** → 计划改为后端自调度
- 后端 `backend/douyin-processor/src/server/main.py` 已经有 APScheduler 实例在跑 cleanup 任务（每天 03:07），复用同一个 scheduler 即可。
- 既有的异步入口 `_run_process_pending()`（`endpoints.py:169`）已经带 `_process_lock` 防重入，无需重复处理。

## Scope

**在范围内**（必须做）：
- `backend/douyin-processor/src/server/main.py`：在 lifespan 里给同一个 APScheduler 加两个 cron job（09:45、17:15 北京时间）调用 `_run_process_pending()`
- `backend/douyin-processor/config/app.yaml`：新增 `process_pending` 配置块（cron 表达式 + timezone），与既有 `cleanup` 块风格保持一致
- `backend/douyin-processor/docs/API接口文档.md`（如有相关描述）：记录「自动调度」已生效

**不在范围内**（明确不做）：
- 前端"待处理 (N)"按钮：保留不变（应急通道）
- `POST /api/process/pending` API：保留不变（手动 + 应急通道）
- n8n webhook 停用：本仓无法控制，用户自行处理
- 处理逻辑本身（`processor.process_pending()`）：零改动
- 修改 `_run_process_pending()`：零改动

## Requirements

### R1 — APScheduler 新增 process_pending 任务
- 在 `main.py` lifespan 内，复用既有 `AsyncIOScheduler` 实例，add_job 两个 cron：
  - `process_pending_morning`：每天 09:45 北京时间
  - `process_pending_evening`：每天 17:15 北京时间
- 调度函数复用 `endpoints._run_process_pending()`（带锁）
- scheduler.start() 后日志打印新调度信息（沿用 cleanup 的格式）

### R2 — app.yaml 新增 process_pending 配置块
- 在 `cleanup` 块旁边加 `process_pending` 块，至少包含：
  - `cron_morning: "45 9 * * *"`
  - `cron_evening: "15 17 * * *"`
  - `timezone: "Asia/Shanghai"`
- 用与 `cleanup` 块相同的注释风格说明用途

### R3 — 启动时并发安全
- 启动顺序：lifespan 先 `set_processor(video_processor)` → 再 `scheduler.add_job()` → 再 `scheduler.start()`
- 调度 callback 调 `_run_process_pending()` 时 processor 已就绪
- 与既有 cleanup 任务不冲突（锁 + 异步串行处理天然安全）

### R4 — 日志可观测
- scheduler.start() 后打印两次调度信息，类似：
  ```
  APScheduler 已注册 process_pending: 09:45 (北京时间)
  APScheduler 已注册 process_pending: 17:15 (北京时间)
  ```
- 触发后日志走 `processor.process_pending()` 既有的 `logger.info("开始处理 pending 视频")` 等

## Acceptance Criteria

- [ ] `config/app.yaml` 新增 `process_pending` 配置块，含 morning / evening / timezone
- [ ] `main.py` lifespan 给同一个 AsyncIOScheduler add 两个 cron job（09:45、17:15）
- [ ] 两个 cron job 都调 `endpoints._run_process_pending()`（带锁版本）
- [ ] 启动日志能看到两个新调度信息
- [ ] 启动失败时原 cleanup 调度不受影响（独立性）
- [ ] 本地起服务后，能在 `logs/` 看到 scheduler 启动日志
- [ ] 手动 `POST /api/process/pending` 仍可用（不破坏既有 API）

## Verification

```bash
# 本地起后端
cd backend/douyin-processor
./.venv/bin/python -m uvicorn src.server.main:app --reload --port 8093

# 观察启动日志：应包含两行 process_pending 调度信息
# 观察 cleanup 调度信息：应仍存在

# 验证 config 解析不报错：
./.venv/bin/python -c "from src.utils import load_config; c=load_config('config/app.yaml'); print(c['app']['process_pending'])"
```

## Notes

- **不删前端按钮 / 不删 API**：保留作为应急通道（v2 也可能用户想手动跑）
- **不删 n8n**：超出本仓范围；停用 n8n 由用户在其他工具完成
- **scheduler 复用 vs 新建**：本任务的 scheduler 必须复用 lifespan 启动的那个，避免双 scheduler 争用 `_process_lock` 引发的潜在竞态
- **计划容器化**：本次只改配置 + 调度注册，无需重新 build 镜像；部署步骤会重启容器让 lifespan 重新执行
