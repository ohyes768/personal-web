"""接口时间戳统一用北京时间（UTC+8，中国无夏令时）。

容器默认 TZ=UTC 时 datetime.fromtimestamp().isoformat() 是 naive UTC，
前端再当本地时间展示就会慢 8 小时（盘后 15:30 显示成 07:30）。
所有 last_updated / 文件 mtime 走这里，必须带 +08:00。
"""
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def now_shanghai() -> datetime:
    return datetime.now(BEIJING)


def now_shanghai_iso() -> str:
    return now_shanghai().isoformat()


def fromtimestamp_shanghai_iso(ts: float) -> str:
    """POSIX 时间戳 → 带 +08:00 的 ISO。不依赖进程 TZ。"""
    return datetime.fromtimestamp(ts, tz=BEIJING).isoformat()
