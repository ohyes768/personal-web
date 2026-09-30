# PRD：housing-map 每周定时刷新房价快照

## 背景

housing-map 后端目前没有任何定时任务机制，房价快照（`price_snapshots.jsonl`）只能靠前端手动点刷新按钮触发 `POST /api/refresh`。实际数据已 15 天未更新（最后 crawled_at 2026-09-15）。

macro 后端已有成熟的 APScheduler 定时任务模式（APScheduler 3.x，`AsyncIOScheduler` + MemoryJobStore）。本任务参考 macro 模式，为 housing-map 加**精简版**定时刷新。

## 需求

每周一 21:17（Asia/Shanghai）自动触发一次全量价格快照刷新，复用现有 `src/services/refresh.py` 的 `start_refresh()`。

### 方案要点（精简版，参考 macro）

1. **依赖**：`pyproject.toml` 加 `apscheduler>=3.10,<4.0`（与 macro 相同约束），`uv sync` 更新 lock。
2. **新模块** `src/scheduler.py`（单文件，预计 ~100 行）：
   - `AsyncIOScheduler`，timezone 统一 `Asia/Shanghai`
   - 注册一个 cron 任务：`17 21 * * mon`（每周一 21:17），任务体调 `refresh_service.start_refresh(0)` 全量刷新
   - job_defaults：`max_instances=1`、`coalesce=True`、`misfire_grace_time=3600`（对齐 macro）
   - 事件监听 `EVENT_JOB_MISSED | EVENT_JOB_ERROR | EVENT_JOB_MAX_INSTANCES`，记日志（沿用现有 `housing-map` logger）
   - 继承 macro 的两个陷阱注释：dow 数字陷阱（APScheduler 3.x 0=周一，用英文缩写 mon）；from_crontab 必须显式传 timezone
   - 提供 `start_scheduler()` / `shutdown_scheduler()`；重入安全（重复 start 忽略）
3. **接线**：`src/main.py` 的 lifespan 中启动 / 关闭 scheduler。
4. **不做**（明确排除）：API 管理路由、JSONL 执行历史、scheduler.json 配置文件、cron 人类可读化、交易日历。手动刷新 API 与前端交互不变。

### 互斥保证

定时任务与手动刷新共用 `refresh.py` 的 `job["running"]` 互斥：若定时触发时已有刷新在跑，`start_refresh` 返回 409 语义，scheduler 侧记一条 warning 日志即可，不排队。

## 验收标准

1. 服务启动后日志显示任务注册（cron 表达式 + 时区），`uvicorn` 正常服务。
2. 单测覆盖（`tests/test_scheduler.py`）：
   - cron 触发时间解析正确：每周一 21:17 Asia/Shanghai，dow 用 `mon` 无歧义（参考 macro `test_scheduler_cron_weekday.py` 的断言思路）
   - 定时任务体在已有刷新运行时不重复启动（调 `start_refresh` 收到 409 时只记日志不抛异常）
   - scheduler start/shutdown 幂等
3. `uv sync && python -m pytest tests/ -v` 全绿（含既有测试）。
4. 手动验证：临时改 cron 为近未来时间点，观察到自动触发一次全量刷新并写盘成功（或以单测 + 代码审查代替，视环境而定）。

## 时间点依据

透明售房网白天更新数据；周一晚上抓可覆盖周末两天的新挂牌/成交，且 21:17 避开整点。具体时点可在实现时调整，默认每周一 21:17。

## 影响范围

- `backend/housing-map/pyproject.toml`、`uv.lock`（新增依赖）
- `backend/housing-map/src/scheduler.py`（新增）
- `backend/housing-map/src/main.py`（lifespan 接线，~4 行）
- `backend/housing-map/tests/test_scheduler.py`（新增）
