"""Web 数据服务每日刷新调度器；简报定时与投递由 Hermes 负责。

APScheduler 3.x，Asia/Shanghai，单实例。cron 星期字段必须用英文名
（fri / mon-fri）：APScheduler 3.x 数字 0=周一，crontab 习惯的 1-5 会被
解析成周二到周六。

关闭语义（spec: scheduler-lifecycle）：APScheduler 3.x shutdown 只有 wait
参数且 AsyncIOExecutor 会取消 pending futures。这里自行跟踪 job Task，
关闭时先有界等待在跑的任务完成，再 shutdown(wait=False)，不用
shutdown(wait=True) 假装 drain。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

JOB_DAILY = "daily_refresh"


class RefreshScheduler:
    def __init__(
        self,
        refresh_fn: Callable[[], Awaitable[object]],
        daily_cron: str = "30 16 * * mon-fri",
    ):
        self._refresh_fn = refresh_fn
        self._daily_cron = daily_cron
        self._scheduler = AsyncIOScheduler(timezone=SHANGHAI_TZ)
        self._tasks: set[asyncio.Task] = set()
        self._closing = False

    def start(self) -> None:
        self._scheduler.add_job(
            self._run_daily,
            CronTrigger.from_crontab(self._daily_cron, timezone=SHANGHAI_TZ),
            id=JOB_DAILY,
            misfire_grace_time=600,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()
        for job in self._scheduler.get_jobs():
            logger.info("调度任务已注册: %s next_run=%s", job.id, job.next_run_time)

    async def _track(self, coro: Awaitable) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        try:
            await task
        finally:
            self._tasks.discard(task)

    async def _run_daily(self) -> None:
        await self._track(self._guarded(JOB_DAILY, self._refresh_fn))

    async def _guarded(self, job_id: str, fn: Callable[[], Awaitable]) -> None:
        if self._closing:
            logger.info("%s 在关闭期间被拒绝", job_id)
            return
        try:
            await fn()
        except Exception:  # noqa: BLE001 — 调度异常必须落日志，不能静默
            logger.exception("调度任务 %s 执行失败", job_id)

    def jobs_info(self) -> list[dict]:
        out = []
        for job in self._scheduler.get_jobs():
            out.append(
                {
                    "id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                }
            )
        return out

    async def shutdown(self, timeout: float = 30.0) -> None:
        """有界 drain：先等在跑任务完成（有超时），再关闭调度器。"""
        self._closing = True
        pending = {t for t in self._tasks if not t.done()}
        if pending:
            _, still_pending = await asyncio.wait(pending, timeout=timeout)
            if still_pending:
                logger.warning("调度任务在 %ss 内未完成，取消: %d 个", timeout, len(still_pending))
                for t in still_pending:
                    t.cancel()
                await asyncio.gather(*still_pending, return_exceptions=True)
        self._scheduler.shutdown(wait=False)
        logger.info("调度器已关闭")
