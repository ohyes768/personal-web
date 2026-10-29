# 基金每周调度设计与实施计划

用户已确认每周六北京时间 07:05 串行刷新四个 tab，替换每日任务；后续批准参照 macro 增加管理页面，不部署。

manager 读取 scheduler.json，使用显式 Asia/Shanghai 和 sat，max_instances=1、coalesce=True、misfire_grace_time=3600。整组通过 asyncio.to_thread 执行。

weekly_refresh 调用现有债基/股基配置名单刷新和市场全量流水线。市场分别使用 bond/stock profile，收益门槛 10/20、规模 5 亿、经理年限 5 年。每项异常不阻断下一项，依据阶段状态和失败计数归类 success/partial/failed。

各项结果与带 +08:00 的开始/结束时间追加到 data/scheduler/weekly_refresh.jsonl，由既有 NAS data volume 持久化。保留数据库 RefreshRun。进程重启不补跑历史周次；现有手动入口不变，不新增跨入口互斥。

## 管理页扩展

`/funds/scheduler` 使用现有暖白色 tokens 和紧凑数据排版，四 tab 共用 header 提供入口。展示一个每周组任务及四项执行范围、启用/暂停、立即执行、下次时间、当前进度和展开历史。5 秒轮询，防重叠请求与连点；错误保留已加载内容并提供重试。

`/api/funds/scheduler/jobs`、PATCH `/jobs/{id}`、POST `/jobs/{id}/run`、GET `/jobs/{id}/runs`；Next catch-all 增加 PATCH/POST 透传。manager 在事件循环内先保留运行标记再创建后台任务，cron 共用标记；当前快照用线程锁保护，由 weekly callback 汇报四项进度。原手动 tab 刷新入口的跨入口互斥仍不扩展。

启停覆盖存储在 `data/scheduler/settings.json`，临时文件+replace，写失败不修改内存状态；不写镜像中的源配置。读取现有周历史，兼容旧记录无 job_id/run_id；忽略损坏行并返回最新在前。禁用只暂停自动调度，允许手动执行，不中止已开始任务。

实施顺序：先写调度、顺序、参数、失败隔离和历史的离线测试并验证红灯，再实现组任务和配置驱动注册；运行新增测试、既有 API/pipeline 测试、ruff 和 diff check；更新契约与验收记录。不提交或部署。回滚无数据库迁移，只需恢复原 manager 和配置。
