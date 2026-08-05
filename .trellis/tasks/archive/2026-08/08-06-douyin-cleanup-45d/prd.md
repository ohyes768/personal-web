# douyin-processor 加 45 天前数据定时清理

## 背景

`backend/douyin-processor` 是被动式后端,视频靠 collector 推过来、ASR 靠管理员手动触发 `POST /api/process/pending`。但目前**没有任何定时清理机制**,旧的 `.wav` 源文件 + `status.json` 记录会无限累积(已确认 `data/output/` 下的转写 JSON 同样永久保留)。

文件存储后端是 file-system-go(外部服务,`https://stock.duomi77.cn:1443`),音频文件由它管;`status.json` 是 douyin-processor 本地。

现有清理 API:
- `POST /api/aweme/cleanup?days=N` — 手动调
- 行为:`status_manager.cleanup_old_records(days)` 找出 `status in (unread/read)` 且 `processed_at < now - N天` 的记录 → 从 `status.json` 硬删 → 调 `filesystem_client.delete_file(f"{aid}.wav")` 删物理文件
- **不删** `data/output/{aweme_id}.json`(转写结果)
- 现有默认 `days=30`

参考实现:rss-relay 的 main.py lifespan 用裸 `AsyncIOScheduler` + 单 job + hardcode cron。本次直接抄。

## 目标

让 douyin-processor **每天凌晨自动清理 45 天前的过期 `.wav` 文件 + status.json 记录**,无需管理员手动调 API。

## 范围

### In Scope

- `pyproject.toml` 加 `apscheduler>=3.10,<4.0` 依赖
- `config/app.yaml` 加 `cleanup` 配置段:`days: 45` + `cron: "7 3 * * *"`(避开整点,跟 rss-relay 03:03 错开 4 分钟减少磁盘 IO 竞争)
- `src/server/main.py` lifespan 加 scheduler:
  - 启动时构造 `AsyncIOScheduler(timezone="Asia/Shanghai")`
  - 注册单 job:`status_manager.cleanup_old_records(days)` + 遍历 `filesystem_client.delete_file()`(复用现有逻辑,**不**走 HTTP self-call,跟 rss-relay 一致)
  - 启动时也跑一次 cleanup(清停机期间过期的数据)
- 关闭时 `await scheduler.shutdown()`(lifespan yield 后)

### Out of Scope

- 清理 `data/output/` 下转写 JSON(本次只清理 .wav + status.json,跟现有手动 API 行为一致)
- 上 dividend-select 同款 SchedulerManager 封装(1 个 job 用不上,过度设计)
- 新增 `set_enabled` / `trigger_now` API(留待以后真要多 job 再说)
- 配置热加载(scheduler.json 那种,本次只读 app.yaml 一次性加载)
- 增加 JSONL 执行历史(小活不需要)

## 需求

### 功能性

| 编号 | 需求 |
|------|------|
| FR-1 | 每天 `cron` 指定时刻自动清理,默认 `7 3 * * *`(北京时间 03:07) |
| FR-2 | 清理阈值 `days=45`,可由 `app.yaml` 配置覆盖 |
| FR-3 | 清理范围:`status in (unread, read)` 且 `processed_at < now - 45天`,跟现有 `POST /api/aweme/cleanup` 行为一致 |
| FR-4 | 删 .wav 物理文件(走 `filesystem_client.delete_file()`)+ 从 `status.json` 硬删 |
| FR-5 | 启动时立即跑一次 cleanup(清停机期间过期数据) |
| FR-6 | 时区显式 `Asia/Shanghai`,**不能**用 UTC 默认值 |
| FR-7 | 清理结果 logger.info:删 N 个文件 + 失败列表 |

### 非功能性

| 编号 | 约束 |
|------|------|
| NFR-1 | 不引新依赖以外的包(只加 apscheduler) |
| NFR-2 | 不破坏现有手动 API `POST /api/aweme/cleanup` 行为 |
| NFR-3 | lifespan 关闭路径必须有 scheduler.shutdown() |
| NFR-4 | apscheduler 版本锁 `>=3.10,<4.0`(dividend-select/rss-relay 用的同一版本区间) |

## 验收标准

- [ ] `pyproject.toml` 依赖加 `apscheduler>=3.10,<4.0`
- [ ] `config/app.yaml` 新增 `cleanup` 段(至少 `days` 和 `cron` 两个字段)
- [ ] `src/server/main.py` lifespan 启动时构造 AsyncIOScheduler + 注册 job
- [ ] 关闭时 `await scheduler.shutdown()`
- [ ] 启动时 logger.info "scheduler started, next run at ..." 输出
- [ ] 启动时立即跑一次 cleanup(日志确认)
- [ ] 调度时区 `Asia/Shanghai`,非 UTC
- [ ] cron 表达式默认 `7 3 * * *`(可由 app.yaml 覆盖)
- [ ] 默认 `days=45`(可由 app.yaml 覆盖)
- [ ] 现有 `POST /api/aweme/cleanup` 手动 API 行为不变(回归对照)
- [ ] `python -c "from src.server.main import app"` OK
- [ ] uvicorn 启动后日志可见 scheduler 启动 + 启动时 cleanup 执行结果
- [ ] 子模块 commit + push,主仓库更新 gitlink commit + push

## 风险

| 风险 | 应对 |
|------|------|
| 跟 rss-relay 同时段磁盘 IO 集中 | cron 故意错开 4 分钟(03:07 vs 03:03) |
| apscheduler 4.x API breaking | 锁版本 `>=3.10,<4.0`,跟 dividend-select 一致 |
| 启动时 cleanup 失败导致 lifespan 启动失败 | try/except 包住,失败 logger.error 不抛(跟 rss-relay 行为一致) |
| 误删 `processed_at` 为空的记录 | `cleanup_old_records` 现有逻辑已校验 `if processed_at and processed_at < cutoff`,安全 |
| 时区没设导致 UTC 偏移 8h | 显式 `timezone="Asia/Shanghai"` |

## 备注

- 参考实现:`backend/rss-relay/src/main.py` lifespan 的 scheduler 段
- 复用现有 `status_manager.cleanup_old_records` + `filesystem_client.delete_file`,**不**走 HTTP self-call(processor 实例已在 lifespan 内构造,自调用多此一举)
- `data/output/` 转写 JSON 永远不清,这是产品决策(用户历史文字稿要能回查),如要清需要新 PRD