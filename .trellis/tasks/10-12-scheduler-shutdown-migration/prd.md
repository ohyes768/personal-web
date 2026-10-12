# 调度器优雅关闭

承接已归档 08-05-scheduler-service 的关闭缺陷。当前部署不涉及 n8n，旧迁移要求已删除。

- [x] 移除 APScheduler.shutdown 不支持的 timeout 参数，实现最多 30 秒等待在跑任务的关闭流程。
- [x] 关闭期间暂停定时调度并拒绝新的手动触发。
- [x] 验证空闲关闭、正常 drain、超时取消、wait=False、重复关闭及重新启动；确认 scheduler 实际停止。

实现说明：APScheduler 3.x AsyncIOExecutor 即使 wait=True 也会取消任务，因此由管理器先跟踪并等待 wrapper，再调用 shutdown(wait=False)，等待停止事件。任务取消采用 asyncio 协作取消；不承诺终止 HTTP 另一端或线程内已开始的刷新。
