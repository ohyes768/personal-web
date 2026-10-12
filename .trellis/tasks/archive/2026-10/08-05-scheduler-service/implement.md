# Implement — dividend-select 内建 APScheduler 定时任务

执行顺序按"先后端骨架 → 后端业务 → 前端 → 部署"分阶段。每个阶段有验证命令和回滚点。

## Phase A：后端 scheduler 模块骨架（不接业务）

### A1. 添加依赖

- `backend/dividend-select/requirements.txt` 加 `apscheduler>=3.10,<4.0` 和 `httpx>=0.27`（如果未装）

**验证**：`pip install -r requirements.txt && python -c "import apscheduler; print(apscheduler.__version__)"`

### A2. 创建模块文件（空函数 + 类型签名）

```
src/scheduler/__init__.py
src/scheduler/manager.py      # SchedulerManager 类骨架
src/scheduler/jobs.py         # 3 个 job 函数（先 raise NotImplementedError）
src/scheduler/history.py      # JSONLReaderWriter 类
src/scheduler/trading_calendar.py  # is_trading_day
src/scheduler/routes.py       # scheduler_router
```

**验证**：`python -c "from src.scheduler import manager, jobs, history, trading_calendar, routes"`

### A3. 实现 history.py

- `JSONLReaderWriter(history_path, max_size_mb=5)`
- 方法：`async append(record: dict) -> None`、`read_tail(job_id: str | None, n: int = 200) -> list[dict]`、`maybe_rotate() -> None`
- 单元测试：写 10 条 → 读回 5 条 → 按 job_id 过滤 → 触发 rotate

**验证**：
```bash
cd backend/dividend-select
python -m pytest tests/test_scheduler_history.py -v
```

### A4. 实现 trading_calendar.py

- 缓存文件 `data/trading_calendar_cache.json` 含 `cached_at` 和 `dates: [...]`
- `is_trading_day(d=None) -> bool` + 降级策略（拉失败用旧缓存；无缓存返回 True + warn）

**验证**：`python -c "from src.scheduler.trading_calendar import is_trading_day; print(is_trading_day())"`

### A5. 实现 manager.py 骨架

- `SchedulerManager(port, config_path, history_path)`
- 方法：`start(services)`, `shutdown(wait, timeout)`, `set_enabled(job_id, enabled)`, `trigger_now(job_id)`, `list_jobs()`, `get_job_runs(job_id, limit)`
- 内部：`AsyncIOScheduler` + `CronTrigger.from_crontab` + 内存里存 jobs_meta
- **job 函数先调通"读 config + 写 history placeholder"**，业务调用留到 Phase B

**验证**：手写脚本 `python -m src.scheduler.smoke_test`：构造一个 `cron="* * * * *"`（每分钟）任务，启动 manager，等 60s 看是否 fire + 写历史

### A6. 接到 main.py lifespan

- 启动末尾 `scheduler = SchedulerManager(...); scheduler.start({"data_reader": data_reader}); app.state.scheduler = scheduler`
- 关闭前 `scheduler.shutdown(wait=True, timeout=30)`
- 修 `docker-compose.nas.yml`、`scripts/start-dividend-dev.bat`、README 明示 `--workers 1`

**验证**：
- `python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8092`
- 启动日志含 "Scheduler 已启动" 和 3 条任务注册信息
- `--workers 2` 启动时拒绝（manager.start 检测 os.environ 或 workers 数）

**🚦 Review Gate 1**：跑 A 阶段全验证 + `pytest tests/` 全过 + 手动启动服务无报错。**不通过不进 Phase B**。

**Rollback point A**：本阶段只新增文件 + 改 main.py 末尾几行，回滚 = 删 `src/scheduler/` + 还原 main.py。

---

## Phase B：后端 job 业务实现

### B1. 实现 jobs.py 三个 job 函数

- `refresh_realtime(job_id, ctx)`：交易日历判断 → codes = ctx.data_reader.get_all_holdings_codes() → `httpx.AsyncClient().post(f"http://127.0.0.1:{port}/api/dividend/realtime/refresh", json={"codes": codes}, timeout=600)` → 200 写 success；非交易日写 skipped
- `refresh_m120(job_id, ctx)`：同结构，路径 `/m120/refresh`，`check_trading_day=False`
- `refresh_dividend(job_id, ctx)`：路径 `/dividend/refresh`，body `{"min_dividend": 10}`，409 → skipped(already_running)

每个 job 函数返回 dict（status/count/error），由 manager 包写入 history。

**验证**：
- 单元测试 mock httpx → 验证 status 映射正确
- 集成测试：启动完整服务 + 手动调 `scheduler.trigger_now("daily_price")` → 等 10s 看 `/api/dividend/scheduler/jobs/daily_price/runs?limit=1` 返回新一条

### B2. 实现 routes.py（scheduler_router）

- `GET /scheduler/jobs`：调 `manager.list_jobs()`，每个 job 附 last_run（来自 history read_tail 1 条）
- `PATCH /scheduler/jobs/{job_id}` body `{enabled: bool}`：调 `manager.set_enabled()` + 写回 config 文件
- `POST /scheduler/jobs/{job_id}/run`：调 `manager.trigger_now()`，返回 202
- `GET /scheduler/jobs/{job_id}/runs?limit=20`：调 `manager.get_job_runs()`

在 main.py `app.include_router(router, prefix='/api/dividend')` 之外**或之内**挂载；选择之内挂载（与 dividend 前缀一致）。

**验证**：curl/Postman 走一遍
```bash
curl http://127.0.0.1:8092/api/dividend/scheduler/jobs
curl -X PATCH http://127.0.0.1:8092/api/dividend/scheduler/jobs/daily_price \
  -H "Content-Type: application/json" -d '{"enabled": false}'
curl -X POST http://127.0.0.1:8092/api/dividend/scheduler/jobs/daily_price/run
curl http://127.0.0.1:8092/api/dividend/scheduler/jobs/daily_price/runs?limit=5
```

### B3. 配置文件初始化

- 写 `backend/dividend-select/config/scheduler.json`（3 个预设任务的 cron 按设计文档）
- 写 `backend/dividend-select/data/.gitkeep` 确保目录存在（scheduler_runs.jsonl 启动时自动建）

**🚦 Review Gate 2**：完整端到端跑一次（启动服务 → 调 trigger_now → 看历史 → 改 enabled → 看下次执行为 null）。**不通过不进 Phase C**。

**Rollback point B**：删 scheduler/ 子模块 + 还原 main.py lifespan + 删 config/scheduler.json。业务接口完全不受影响。

---

## Phase C：前端设置页

### C1. 类型与 API client

- `apps/dividend/src/lib/types.ts` 加 `SchedulerJob` / `SchedulerJobRun`
- `apps/dividend/src/lib/api-client.ts` 加 4 个方法（如已有 api-client 结构对齐 dividend 的 client 模式）

**验证**：`pnpm tsc --noEmit`

### C2. 新建 settings/scheduler 路由与页面

- `apps/dividend/src/app/settings/scheduler/page.tsx`
- 顶部导航加入口（如已有 Settings 入口则挂菜单项）

**验证**：`pnpm dev` → 浏览器打开 `http://localhost:3003/settings/scheduler`

### C3. 任务列表表格

- 列：name / target / cron_human / next_run_time / last_run / enabled Switch / 操作按钮
- Switch 受控，调 PATCH
- last_run 状态用 Badge（success 绿 / skipped 黄 / failed 红）

**验证**：手工切换 enabled → 看后端日志确认 pause/resume → 刷新页面状态保持

### C4. 立即执行按钮

- 弹确认 → POST run → toast → 延迟 3s 后重新拉 history
- 如果 job enabled=false 也允许立即执行（一次性触发，不影响 cron）

**验证**：点击立即执行 → 看 history 列表是否出现新一条

### C5. 历史抽屉

- 点击行展开 / 抽屉显示最近 20 条
- failed 错误信息显示 + 一键复制
- 状态用 timeline 或 list 都行

**🚦 Review Gate 3**：完整流程体验。disabled job 不能自动执行；enabled job 改 cron 后下次执行时间正确；history 完整。

**Rollback point C**：删前端 settings/scheduler 目录 + 还原导航。后端 scheduler 仍能正常工作（只是没 UI）。

---

## Phase D：部署与迁移

### D1. docker-compose.nas.yml 改动

- `dividend-backend` 服务的 command 写死 `--workers 1`
- 环境变量 `SCHEDULER_ENABLED=true`（默认开）
- 挂载卷加 `./backend/dividend-select/config:/app/config` 和 `./backend/dividend-select/data:/app/data`（如果之前没挂 data）

### D2. NAS 部署测试

```bash
# NAS 上
git pull
git submodule update --init --recursive backend/dividend-select
docker compose -f docker-compose.nas.yml build --no-cache dividend-backend
docker compose -f docker-compose.nas.yml up -d --force-recreate dividend-backend
docker compose -f docker-compose.nas.yml logs -f dividend-backend | grep -i scheduler
```

验证：启动日志含 3 个任务注册 + `Scheduler 已启动`；`curl` 4 个 API 都通。

### D3. 双跑对照期（1 周）

- n8n 任务保留不动
- 内建 scheduler 启用
- 每天看 scheduler_runs.jsonl 的执行结果 vs n8n 触发的结果（通过应用日志 / 数据文件 mtime 对照）
- 一致后停掉 n8n 任务

**🚦 Final Gate**：双跑 7 天无异常 → n8n 停用 → 任务完成。

---

## 全局验证清单

执行结束前必须全绿：

- [ ] `cd backend/dividend-select && python -m pytest tests/ -v` 全过（含新增 scheduler 测试）
- [ ] `cd apps/dividend && pnpm lint && pnpm build` 全过
- [ ] 后端启动无 ERROR 日志
- [ ] 4 个 scheduler API curl 全通
- [ ] 前端 settings/scheduler 页面 3 个任务正常显示
- [ ] 启用/禁用 / 立即执行 / 历史查看全流程跑通
- [ ] docker-compose.nas.yml 部署 NAS 成功

## 注意事项

- 不要在 Phase A/B 期间下线 n8n，否则会出现"无定时刷新"窗口期
- 数据文件 `config/scheduler.json` 和 `data/scheduler_runs.jsonl` 都不能进 .gitignore（前者是代码配置需提交，后者是运行时数据按现有 data/ 目录规则处理）
- 任何阶段卡住先回到上一个 🚦 Review Gate，不要硬推下一步
