# Design — dividend-select 内建 APScheduler 定时任务

## 模块边界

```
backend/dividend-select/
├── config/
│   └── scheduler.json              # source of truth：3 个任务的 cron 与 enabled
├── data/
│   └── scheduler_runs.jsonl        # 执行历史（append-only）
└── src/
    ├── scheduler/
    │   ├── __init__.py
    │   ├── manager.py              # SchedulerManager：注册/启停/立即执行/启用禁用
    │   ├── jobs.py                 # 3 个 job 函数（包业务调用 + 交易日历判断 + 异常映射）
    │   ├── history.py              # JSONL 读写 + 滚动
    │   ├── trading_calendar.py     # 交易日历缓存（akshare 拉 + 一年缓存）
    │   └── routes.py               # /api/dividend/scheduler/* 路由（也可挂到主 router）
    └── main.py                     # lifespan 增加 scheduler.start/scheduler.shutdown
```

scheduler 模块**单向依赖** service 层，service 层不感知 scheduler。

## scheduler 与业务的关系：HTTP self-call（推荐）

3 个目标接口本身已经为"被外部定时触发"设计（入参简洁、`_is_refreshing` 锁、错误处理完备），scheduler 把自己当作"内部 n8n"，**直接 HTTP 调本地接口**：

```python
async def _call_self(method: str, path: str, json_body: dict | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=600) as c:
        return await c.request(method, f"http://127.0.0.1:{self._port}/api/dividend{path}", json=json_body)
```

| 方案 | 优点 | 缺点 |
|------|------|------|
| **A. HTTP self-call** ✅ | 零侵入现有 routes；复用所有并发锁/错误处理；和 n8n 调用语义完全一致 | 依赖服务已 ready；要走 TCP 栈 |
| B. 抽 service 层函数 | 调用更直接 | 要重构 routes.py 的 dividend refresh（业务大段），改造范围翻倍 |

**选 A**。`base_url` 用 `http://127.0.0.1:{AppConfig.get_server_port()}`；启动顺序保证：lifespan 启动末尾再 `scheduler.start()`，确保 uvicorn 已经监听端口（FastAPI lifespan 在 startup 阶段执行，此时 socket 已绑定）。

## 数据流

```
启动：
  main.py lifespan
    ├── 初始化 services (data_reader, m120_service, ...)
    ├── set_services(...)
    ├── scheduler = SchedulerManager(port, services)
    └── scheduler.start()
         ├── 读 config/scheduler.json
         ├── 注册 3 个 cron job（disabled 的 add 后立即 pause_job）
         └── AsyncIOScheduler.start()

定时触发：
  CronTrigger fire
    └── jobs.refresh_realtime(job_id="daily_price")
         ├── 读 trading_calendar.is_trading_day(today) → False 则写 skipped 历史 return
         ├── codes = data_reader.get_all_holdings_codes()
         └── resp = _call_self("POST", "/realtime/refresh", {"codes": codes})
              ├── 200 → 写 success 历史 + count
              ├── 409 → 写 skipped(already_running) 历史（仅 dividend）
              └── 5xx → 写 failed 历史 + error

启用/禁用：
  PATCH /api/dividend/scheduler/jobs/{id} {enabled: false}
    ├── config_writer.update_enabled(id, false)  # 改 config/scheduler.json
    └── scheduler.pause_job(id) 或 resume_job(id)

立即执行：
  POST /api/dividend/scheduler/jobs/{id}/run
    └── scheduler.add_job(jobs.xxx, trigger="date", run_date=now)  # 一次性任务
         （立即返回 202，结果通过历史接口查）

优雅关闭：
  lifespan yield
    └── scheduler.shutdown(wait=True)  # 等在跑任务，最长 wait_time
```

## cron → 中文可读：`cron_human.py`

独立工具模块，输入 cron 表达式（5 字段）输出中文描述。覆盖常见模式，无法识别时返回原字符串。

```python
def cron_to_human(cron: str) -> str:
    """
    支持：
      30 15 * * 1-5  → "每周一至周五 15:30"
      0 2 * * 6      → "每周六 02:00"
      0 2 1 * *      → "每月 1 日 02:00"
      0 0 * * *      → "每天 00:00"
      */5 * * * *    → "每 5 分钟"
      0 */2 * * *    → "每 2 小时的 0 分"
      其他           → 返回原 cron 字符串
    """
```

实现策略：解析 5 字段为 `[m, h, dom, mon, dow]`，按优先级匹配：
1. dom != `*` && mon == `*` && dow == `*` → "每月 N 日 HH:MM"
2. dow 含范围/列表（如 `1-5` / `6` / `0,6`）→ "每周X HH:MM"
3. dom/mon/dow 全 `*` → "每天 HH:MM"
4. h 或 m 含 `*/N` → "每 N 分钟/小时..."
5. 兜底返回原串

dow 中文映射：`0/7`→日、`1`→一、`2`→二、`3`→三、`4`→四、`5`→五、`6`→六；范围 `1-5` → "一至周五"。

放在 `src/scheduler/cron_human.py`，前端不需要此模块（直接用 API 返回的 `cron_human` 字段）。

## 配置文件 schema：`config/scheduler.json`

```json
{
  "version": 1,
  "jobs": [
    {
      "id": "daily_price",
      "name": "每日刷新实时价格",
      "target": "refresh_realtime",
      "cron": "30 15 * * 1-5",
      "enabled": true,
      "check_trading_day": true,
      "description": "A 股 15:00 收盘后半小时刷价格 + 触发挡位告警"
    },
    {
      "id": "weekly_m120",
      "name": "每周刷新 M120 均线",
      "target": "refresh_m120",
      "cron": "0 2 * * 6",
      "enabled": true,
      "check_trading_day": false,
      "description": "周六 02:00 跑 M120 重算（非交易日也跑，周末一次覆盖上周）"
    },
    {
      "id": "monthly_dividend",
      "name": "每月刷新股息率核心数据",
      "target": "refresh_dividend",
      "cron": "0 2 1 * *",
      "enabled": true,
      "check_trading_day": false,
      "params": {"min_dividend": 10},
      "description": "每月 1 号 02:00 重算持仓 + 分红 + 股息率"
    }
  ]
}
```

**设计选择**：
- `check_trading_day` 是字段而非全局开关，因为 M120 周末跑、dividend 月初跑都不该 skip，只有价格刷要 skip
- `params` 字段透传到接口 body，对应 `RefreshRequest{min_dividend}` 这种结构
- 改 cron 改 enabled 都改这个文件，文件是 source of truth，scheduler 内存只是缓存

## JSONL 历史 schema：`data/scheduler_runs.jsonl`

每行一条记录：

```json
{"job_id":"daily_price","target":"refresh_realtime","start":"2026-08-05T15:30:00+08:00","end":"2026-08-05T15:31:24+08:00","status":"success","count":187,"error":null}
{"job_id":"daily_price","target":"refresh_realtime","start":"2026-08-06T15:30:00+08:00","end":"2026-08-06T15:30:01+08:00","status":"skipped","reason":"non_trading_day","error":null}
{"job_id":"monthly_dividend","target":"refresh_dividend","start":"2026-08-01T02:00:00+08:00","end":"2026-08-01T02:00:01+08:00","status":"skipped","reason":"already_running","error":null}
{"job_id":"weekly_m120","target":"refresh_m120","start":"2026-08-08T02:00:00+08:00","end":"2026-08-08T02:05:30+08:00","status":"failed","error":"ConnectionError: ..."}
```

**status 枚举**：`success | skipped | failed`
**reason（仅 skipped 用）**：`non_trading_day | already_running`

**写入**：
- `asyncio.Lock` 串行化追加，避免并发交错
- `open(..., "a", encoding="utf-8")` + 单次 `write(line + "\n")` + `flush()`
- 写入失败 try/except + log warning，不影响主流程（NFR-6）

**滚动**：
- 启动时检查文件大小，超过 5MB → rename 为 `scheduler_runs.YYYYMMDD.jsonl`，开新文件
- 旧文件不主动删，由用户/部署侧清理（兜底：保留最近 3 个归档）

**读取**：
- `tail -n 200` 风格：从尾部往前读 200 行（`seek + 反向 chunked read`）
- 解析失败的行跳过但不抛
- 按 `job_id` 过滤后回前端

## API 契约

新增 prefix `/api/dividend/scheduler`（在 routes.py 主 router 下挂子 router，或新 module）：

### `GET /api/dividend/scheduler/jobs`

返回所有任务列表：

```json
{
  "jobs": [
    {
      "id": "daily_price",
      "name": "每日刷新实时价格",
      "target": "refresh_realtime",
      "cron": "30 15 * * 1-5",
      "cron_human": "每周一至周五 15:30",
      "enabled": true,
      "next_run_time": "2026-08-06T15:30:00+08:00",
      "last_run": {
        "start": "2026-08-05T15:30:00+08:00",
        "status": "success",
        "count": 187,
        "error": null
      }
    },
    ...
  ]
}
```

### `PATCH /api/dividend/scheduler/jobs/{job_id}`

body：`{"enabled": bool}`

返回更新后的 job 对象（同上单条结构）。

**404** 如果 job_id 不存在。
**409** 如果试图修改内置任务的 cron（虽然前端不发，但兜底）。

### `POST /api/dividend/scheduler/jobs/{job_id}/run`

立即执行（异步，立即返回 202）：

```json
{"message": "已触发", "job_id": "daily_price", "triggered_at": "2026-08-05T16:00:00+08:00"}
```

通过 `scheduler.add_job(..., trigger='date', run_date=datetime.now())` 实现一次性触发，job_id 加后缀避免与 cron job 冲突。

### `GET /api/dividend/scheduler/jobs/{job_id}/runs?limit=20`

返回最近 N 条历史：

```json
{
  "job_id": "daily_price",
  "runs": [
    {"start": "...", "end": "...", "status": "success", "count": 187, "error": null},
    {"start": "...", "end": "...", "status": "skipped", "reason": "non_trading_day", "error": null},
    ...
  ],
  "total_returned": 20
}
```

## 交易日历模块：`trading_calendar.py`

```python
import akshare as ak
from datetime import date, timedelta
from pathlib import Path
import json

CACHE_PATH = Path("data/trading_calendar_cache.json")

def is_trading_day(d: date | None = None) -> bool:
    """判断 d（默认今天）是否是 A 股交易日"""
    d = d or date.today()
    cal = _load_or_refresh_calendar()
    return d.isoformat() in cal

def _load_or_refresh_calendar() -> set[str]:
    """
    缓存策略：
    - 缓存文件存在 且 距离上次刷新 < 30 天 → 直接用
    - 否则：尝试 ak.tool_trade_date_hist_sina() 拉新
    - 拉失败时：用旧缓存（warn），没有缓存就退化返回全 True（宁错杀）
    """
    ...
```

## lifespan 改动（main.py）

```python
# 启动末尾
from src.scheduler.manager import SchedulerManager
scheduler = SchedulerManager(
    port=AppConfig.get_server_port(),
    config_path=PROJECT_ROOT / "config" / "scheduler.json",
    history_path=AppConfig.DATA_DIR / "scheduler_runs.jsonl",
)
scheduler.start(services={"data_reader": data_reader})  # 现拉 codes 用
app.state.scheduler = scheduler
logger.info("Scheduler 已启动")

yield

# 关闭
logger.info("等待 scheduler 关闭...")
scheduler.shutdown(wait=True, timeout=30)
```

## 前端改动（apps/dividend）

### 路由

新增 `apps/dividend/src/app/settings/scheduler/page.tsx`，加导航入口（顶部图标 / 设置菜单项）。

### 数据层

`src/lib/api-client.ts` 增加 4 个方法：

```ts
listSchedulerJobs(): Promise<SchedulerJob[]>
patchSchedulerJob(id: string, enabled: boolean): Promise<SchedulerJob>
runSchedulerJobNow(id: string): Promise<{ triggered_at: string }>
listSchedulerJobRuns(id: string, limit?: number): Promise<SchedulerJobRun[]>
```

`src/lib/types.ts` 增加 `SchedulerJob` / `SchedulerJobRun` 类型。

### UI 组件结构

```
app/settings/scheduler/page.tsx
├── 任务列表卡片（table）
│   ├── 任务名 / target / cron_human
│   ├── 启用/禁用 Switch（受控，调 patch）
│   ├── 下次执行时间
│   ├── 上次执行结果（success/skipped/failed + count/reason）
│   └── 操作：[立即执行] [展开历史]
└── 抽屉或折叠面板（每个 job 一组）
    └── 最近 20 条历史时间线
```

**交互细节**：
- Switch 切换 → 立即 PATCH，失败回滚 + toast
- 立即执行 → 弹确认 → POST run → toast"已触发，几秒后刷新" → 列表 3s 后轮询一次新历史
- 历史默认折叠，点开懒加载
- failed 状态错误信息可点击复制

## 部署约束

- `--workers 1` 必须显式声明（启动脚本 + docker-compose + README）
- Dockerfile 内 `CMD` 写死 `--workers 1`
- 启动日志第一行打 `WARNING: scheduler requires --workers 1`（如果检测到 workers > 1，启动时拒绝）

## 兼容性 & 回滚

- 旧 n8n 任务保留至少 1 周，与内建 scheduler 双跑对照
- 前端调度页与 n8n 独立，互不影响
- 若需紧急回滚：禁用所有 scheduler 任务（PATCH enabled=false 或编辑 config/scheduler.json），重启服务，回退到 n8n 触发
- scheduler_runs.jsonl 不删，作为审计日志保留

## 已知风险

1. **HTTP self-call 端口绑定时机**：lifespan 启动阶段 socket 已绑定但 server 还没"接受请求"？需测试。备选：scheduler 首次启动延迟 5s，或使用 `asyncio.sleep(2)` + 首次 health check self-call
2. **akshare 交易日历接口偶发失败**：缓存 + warn 降级
3. **JSONL 并发写**：Lock 串行化 + POSIX append 原子兜底
4. **dividend refresh 长耗时（30s-5min）**：APScheduler `misfire_grace_time` 设大（如 3600s）避免错过窗口直接丢弃；`max_instances=1` 防止重入
5. **codes 为空**：data_reader 没数据时 job 仍调用接口传空数组？接口应能优雅处理（routes 现有逻辑需验证；不能则 job 函数加 `if not codes: return skipped`）

## 不在本次设计范围

- cron 编辑 UI（PRD 明确不做）
- 跨服务（douyin / global-macro）调度
- 分布式锁
- 告警/通知（钉钉已有 alert_service，独立链路）
