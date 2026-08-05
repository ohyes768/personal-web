# dividend-select 内建 APScheduler 定时任务与可视化设置页

## 背景

dividend-select 当前的定时刷新由外部 n8n 触发，调后端的 `POST /api/dividend/refresh`、`POST /api/dividend/m120/refresh`、`POST /api/dividend/realtime/refresh` 三个接口。跨服务编排增加了部署/维护成本（n8n 单独部署、跨网络调用、出错排查链路长），决定把定时任务内化到 dividend-select 服务自身。

## 目标

- 后端内建 scheduler，按预设 cron 自动触发上述 3 个刷新接口
- 无需引入 SQLite/Redis 等外部存储，对齐项目"零数据库"现状
- 前端 dividend 加设置页，可视化查看任务列表、状态、最近执行历史
- 前端支持启用/禁用任务、立即手动执行
- **不做** cron 编辑（cron 由配置文件管，避免误改触发频率）

## 范围

### In Scope

- 后端 `src/scheduler/` 新模块：APScheduler + MemoryJobStore
- 任务配置文件（source of truth），含 3 个预设任务的 cron
- JSONL 文件记录每次执行结果（job_id / 起止时间 / 状态 / 错误信息）
- 后端 REST API：
  - 任务列表（含 cron、enabled、next_run_time、last_run_summary）
  - 启用/禁用单个任务
  - 立即手动执行单个任务
  - 单个任务的最近 N 条执行历史
- 前端 `apps/dividend` 新增设置页（路由 `/settings/scheduler` 或对等入口）
  - 表格：任务名 | 目标接口 | cron | 状态（启用/禁用）| 下次执行 | 上次执行结果 | 操作
  - 操作：启用/禁用开关、立即执行按钮、查看历史
  - 历史展示：最近 N 条（时间 / 状态 / 耗时 / 错误信息）
- 交易日历判断（job 函数内部）：A 股节假日 skip 价格刷新与 M120 刷新；股息率刷新不受交易日历影响

### Out of Scope

- cron 表达式在线编辑（明确不做，避免误改触发频率）
- 动态创建/删除任务（任务集合是固定的 3 个）
- 跨服务（douyin / global-macro）的定时任务，本次只迁 dividend-select
- 分布式锁 / 多 worker 并发安全（部署约束文档化为"单 worker 模式"）
- 邮件/钉钉告警（已有的 alert_service 不在本次范围扩展）

## 需求

### 功能性

| 编号 | 需求 |
|------|------|
| FR-1 | 服务启动时从 `config/scheduler.json`（或同义路径）加载 3 个预设任务并注册到 scheduler |
| FR-2 | 服务停止时优雅关闭 scheduler（drain 在跑任务，等待最多 N 秒） |
| FR-3 | 任务函数执行时**现从 `data_reader` 读当前持仓 codes**，不依赖配置文件写死的 codes 列表 |
| FR-4 | 价格刷新、M120 刷新执行前先判断交易日历；非交易日 skip 并记录一条 `status=skipped` 的历史 |
| FR-5 | 股息率刷新触发时如撞到 `_is_refreshing` 锁（接口 409），记录 `status=skipped, reason=already_running`，不视为失败 |
| FR-6 | 启用/禁用操作立即生效（写到配置 + scheduler 暂停/恢复 job） |
| FR-7 | 立即执行按钮触发异步执行，不阻塞 API 响应；执行结果通过历史接口查询 |
| FR-8 | JSONL 历史结构稳定，至少包含：`job_id, target, start, end, status, count, error` |
| FR-9 | 历史文件大小控制：超过阈值时自动滚动（保留最近 N 条，旧文件归档或截断） |
| FR-10 | 任务列表 API 返回 `cron_human` 字段：将 cron 表达式转中文可读描述（如 `30 15 * * 1-5` → `每周一至周五 15:30`），无法识别的模式兜底返回原 cron 字符串 |

### 非功能性

| 编号 | 约束 |
|------|------|
| NFR-1 | 新依赖仅 `apscheduler` 一个 PyPI 包 |
| NFR-2 | 不引入 SQLite / Redis / 任何外部存储 |
| NFR-3 | scheduler 模块与现有 routes/services 解耦，不污染现有 service 代码 |
| NFR-4 | 部署约束：uvicorn 必须 `--workers 1`，文档 + 启动脚本都明示这一点 |
| NFR-5 | 配置文件改动需可观测：reload 操作记录日志，旧 cron 与新 cron 都打印 |
| NFR-6 | 执行历史写入失败不得影响主流程（catch + warn） |

## 验收标准

### 后端

- [ ] 启动日志能看到 3 个任务注册成功，含 cron 与下次执行时间
- [ ] `GET /api/scheduler/jobs` 返回 3 条任务，字段齐全
- [ ] `PATCH /api/scheduler/jobs/{id}` body `{"enabled": false}` 后，scheduler 内 job 被暂停，下次执行时间变为 null
- [ ] `POST /api/scheduler/jobs/{id}/run` 立即触发，返回 202；几秒后 `GET /api/scheduler/jobs/{id}/runs` 能看到新一条记录
- [ ] 非交易日触发价格刷新 → JSONL 出现 `status=skipped`
- [ ] 股息率刷新撞锁 → JSONL 出现 `status=skipped, reason=already_running`，不重试不报错
- [ ] 服务停止 → 在跑任务能在 30s 内 drain 完成

### 前端

- [ ] 设置页能展示 3 条任务，cron / 下次执行 / 上次结果与后端一致
- [ ] 启用/禁用开关切换 → 后端 PATCH 成功 → UI 状态同步刷新
- [ ] 立即执行按钮点击 → 弹 toast 提示"已触发" → 历史列表 N 秒内出现新记录（轮询或手动刷新）
- [ ] 历史展开后展示最近 20 条，失败记录的错误信息可复制

### 部署/迁移

- [ ] NAS 部署文档（`docker-compose.nas.yml` 注释或 README）明示 scheduler 模块需 `--workers 1`
- [ ] 旧 n8n 任务保留至少 1 周双跑对照期，验证内建 scheduler 触发结果与 n8n 一致后再下线 n8n

## 风险与已知约束

1. **多 worker 风险**：APScheduler 在多 worker 部署时会每个进程各起一份，导致重复执行。本次用部署约束（`--workers 1`）兜底，不引入 Redis 锁。
2. **交易日历数据源**：`akshare.tool_trade_date_hist_sina()` 拉取可能失败。降级策略：缓存上一年历，失败时 warn 但仍执行 job（宁错杀不放过）。
3. **JSONL 并发写**：APScheduler 多个 job 可能并发写同一文件。用 `asyncio.Lock` 或文件追加模式（POSIX 下小写入原子）兜底。
4. **持仓 codes 来源**：依赖 `data_reader` 在 scheduler 启动时已初始化；main.py 启动顺序需保证。

## 相关接口（现状）

- `POST /api/dividend/realtime/refresh` body `{"codes":[...]}` — 每日价格 + 挡位告警
- `POST /api/dividend/m120/refresh` body `{"codes":[...]}` — M120 数据
- `POST /api/dividend/refresh` body `{"min_dividend":10}` — 股息率核心数据，已有 `_is_refreshing` 锁

## 备注

- 技术设计见 `design.md`，执行计划见 `implement.md`
