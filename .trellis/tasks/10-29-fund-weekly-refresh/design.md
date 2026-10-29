# 设计

`scheduler.json` 四项refresh_tab任务，明确tab/cron/cron_human。manager为每job维护running/current_run/last_record；触发前立即保留标记，创建任务后等待共享asyncio.Lock，再to_thread调用refresh_tab_sync。queued/running区分等待与采集；同job重复冲突，不同job排队。源配置不写运行态。

采集器参数沿用原页面默认，每次仅一tab，历史继续追加到原JSONL。读取以job_id隔离；旧组记录按items.tab投影自身状态/开始结束时间。旧整体暂停fallback应用四项，新id覆盖优先，原子保存四项设置。

FundsHeader右侧Cog6ToothIcon按钮挂载SchedulerDialog。原生showModal进入top layer，背景不可交互；显式恢复入口焦点与body滚动。宽度calc(100% - 2rem)、最大56rem、高度90dvh，内容滚动、标题和关闭按钮固定。四行任务独立操作和历史，5秒轮询只在挂载期间，AbortController与版本号丢弃过期请求。旧scheduler页server redirect到/bond?scheduler=1。

不改变原tab独立刷新入口的互斥边界；不修改其他任务代码或自动部署。回滚需同时恢复旧配置/manager/采集入口和管理页；数据文件兼容保留。
