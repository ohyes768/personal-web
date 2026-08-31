"""调度器统一用北京时间（UTC+8，中国无夏令时）。

容器默认 TZ=UTC 时 datetime.now() 是 naive UTC，isoformat() 不带偏移，
前端再当本地时间展示就会慢 8 小时。所有 scheduler 落盘时间戳走这里。
"""

from datetime import datetime, timedelta, timezone

# APScheduler CronTrigger / AsyncIOScheduler 用 IANA 名；落盘用固定 UTC+8。
SCHEDULER_TZ_NAME = "Asia/Shanghai"
BEIJING = timezone(timedelta(hours=8))


def now_shanghai() -> datetime:
    return datetime.now(BEIJING)


def now_shanghai_iso() -> str:
    return now_shanghai().isoformat()
