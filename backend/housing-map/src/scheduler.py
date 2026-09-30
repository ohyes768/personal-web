"""定时任务：每周一 21:17 (Asia/Shanghai) 自动全量刷新价格快照。

精简自 macro 的 src/scheduler/ 模块（无 API 管理路由 / 执行历史 / cron 文案化）。
任务体复用 services.refresh.start_refresh(0)，其 job["running"] 互斥保证
定时触发与前端手动刷新不会并发跑两份采集。

两个从 macro 继承的陷阱：
- 时区：from_crontab 不传 timezone 会落到系统默认时区（容器内为 UTC），
  触发时间偏移 8 小时。scheduler 与 trigger 必须共用同一时区。
- dow 数字：APScheduler 3.x 的 CronTrigger 0=周一（Python 习惯），不是
  crontab 的 0=周日。星期一律写英文缩写（mon），不用数字。
"""

import logging

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.services import refresh as refresh_service

logger = logging.getLogger("housing-map")

SCHEDULER_TIMEZONE = "Asia/Shanghai"
# 每周一 21:17：透明售房网白天更新数据，周一晚抓覆盖周末两天；避开整点
REFRESH_CRON = "17 21 * * mon"
JOB_ID = "weekly_price_refresh"

_scheduler: AsyncIOScheduler | None = None


async def run_weekly_refresh() -> None:
    """APScheduler 入口：全量刷新；已有刷新在跑时只记日志（409 不算错误）。"""
    ok, status, body = await refresh_service.start_refresh(0)
    if ok:
        logger.info(f"[{JOB_ID}] 定时刷新已启动: {body.get('data')}")
    elif status == 409:
        logger.warning(f"[{JOB_ID}] 已有刷新任务在运行，本次定时触发跳过")
    else:
        # 500 等：记 error 但不抛，避免 APScheduler 把 job 标记为出错后刷屏重试日志
        logger.error(f"[{JOB_ID}] 定时刷新启动失败: {body.get('error')}")


def _on_scheduler_event(event) -> None:
    if event.code == EVENT_JOB_MISSED:
        logger.warning(f"[{event.job_id}] 错过触发时间 (misfire)")
    elif event.code == EVENT_JOB_ERROR:
        logger.error(f"[{event.job_id}] 执行出错: {event.exception}")
    elif event.code == EVENT_JOB_MAX_INSTANCES:
        logger.warning(f"[{event.job_id}] 上一轮还没跑完，本轮跳过")


def start_scheduler() -> None:
    """lifespan 启动时调用；重复调用只记警告不重复建。"""
    global _scheduler
    if _scheduler is not None:
        logger.warning("scheduler 已启动，忽略 start_scheduler")
        return
    scheduler = AsyncIOScheduler(
        timezone=SCHEDULER_TIMEZONE,
        job_defaults={
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 3600,
        },
    )
    scheduler.add_job(
        run_weekly_refresh,
        CronTrigger.from_crontab(REFRESH_CRON, timezone=SCHEDULER_TIMEZONE),
        id=JOB_ID,
        replace_existing=True,
    )
    scheduler.add_listener(
        _on_scheduler_event,
        EVENT_JOB_MISSED | EVENT_JOB_ERROR | EVENT_JOB_MAX_INSTANCES,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(f"[{JOB_ID}] 注册: cron={REFRESH_CRON} tz={SCHEDULER_TIMEZONE}")


def shutdown_scheduler() -> None:
    """lifespan 关闭时调用；未启动时静默（幂等）。"""
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("scheduler 已关闭")
