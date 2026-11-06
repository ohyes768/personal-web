"""douyin-processor 内建调度管理包（参照 dividend-select/macro 的 src/scheduler 模式）

- manager.SchedulerManager：注册 / 启停 / 立即执行 / 历史
- routes：/api/scheduler/* 4 个管理 API
- jobs：JOB_SPECS 定义 + 进程内直调 target + 唯一处理锁 _process_lock
- history：JSONL 执行历史（5MB 滚动归档）
- cron_human：cron → 中文可读描述
"""
