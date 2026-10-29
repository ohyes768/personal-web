"""轻量调度器：周报触发 + 每日刷新。

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
from datetime import datetime
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

JOB_WEEKLY = "weekly_report"
JOB_DAILY = "daily_refresh"


class ReportScheduler:
    def __init__(
        self,
        weekly_fn: Callable[[], Awaitable[dict]],
        refresh_fn: Callable[[], Awaitable[object]],
        report_cron: str = "0 19 * * fri",
        daily_cron: str = "30 16 * * mon-fri",
    ):
        self._weekly_fn = weekly_fn
        self._refresh_fn = refresh_fn
        self._report_cron = report_cron
        self._daily_cron = daily_cron
        self._scheduler = AsyncIOScheduler(timezone=SHANGHAI_TZ)
        self._tasks: set[asyncio.Task] = set()
        self._closing = False

    def start(self) -> None:
        self._scheduler.add_job(
            self._run_weekly,
            CronTrigger.from_crontab(self._report_cron, timezone=SHANGHAI_TZ),
            id=JOB_WEEKLY,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
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

    async def _run_weekly(self) -> None:
        await self._guarded(JOB_WEEKLY, self._weekly_fn)

    async def _run_daily(self) -> None:
        await self._guarded(JOB_DAILY, self._refresh_fn)

    async def _guarded(self, job_id: str, fn: Callable[[], Awaitable]) -> None:
        if self._closing:
            logger.info("%s 在关闭期间被拒绝", job_id)
            return
        try:
            await fn()
        except Exception:  # noqa: BLE001 — 调度异常必须落日志，不能静默
            logger.exception("调度任务 %s 执行失败", job_id)

    async def trigger(self, job_id: str) -> dict:
        """手动触发（API 入口）。关闭期间拒绝新任务。"""
        if self._closing:
            raise RuntimeError("调度器正在关闭，拒绝手动触发")
        if job_id == JOB_WEEKLY:
            await self._track(self._guarded(JOB_WEEKLY, self._weekly_fn))
            return {"job_id": JOB_WEEKLY, "triggered_at": datetime.now(SHANGHAI_TZ).isoformat()}
        if job_id == JOB_DAILY:
            await self._track(self._guarded(JOB_DAILY, self._refresh_fn))
            return {"job_id": JOB_DAILY, "triggered_at": datetime.now(SHANGHAI_TZ).isoformat()}
        raise KeyError(f"未知任务: {job_id}")

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
            done, still_pending = await asyncio.wait(pending, timeout=timeout)
            if still_pending:
                logger.warning("调度任务在 %ss 内未完成，取消: %d 个", timeout, len(still_pending))
                for t in still_pending:
                    t.cancel()
        self._scheduler.shutdown(wait=False)
        logger.info("调度器已关闭")
