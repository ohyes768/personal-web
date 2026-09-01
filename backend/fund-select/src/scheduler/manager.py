"""
APScheduler 管理器（每日刷新配置名单）

调度形态对齐 dividend 的 scheduler.json；v1 仅一个每日任务。
"""
import asyncio
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.utils.config import PROJECT_ROOT
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.scheduler")

SCHEDULER_CONFIG = PROJECT_ROOT / "src" / "scheduler" / "scheduler.json"


class SchedulerManager:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    def start(self, app) -> None:
        # 每日 07:05 拉取配置名单（债基净值一般前一晚已更新）
        self.scheduler.add_job(
            self._daily_refresh,
            CronTrigger(hour=7, minute=5, timezone="Asia/Shanghai"),
            id="daily_fund_refresh",
            name="每日刷新配置名单基金",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("Scheduler 已启动：daily_fund_refresh @ 07:05 Asia/Shanghai")

    async def _daily_refresh(self) -> None:
        # 采集是同步阻塞的（requests/akshare），放线程池执行
        from src.scheduler.tasks import refresh_configured_funds_sync

        logger.info("定时刷新开始")
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, refresh_configured_funds_sync
            )
        except Exception:
            logger.exception("定时刷新失败")
        logger.info("定时刷新结束 %s", datetime.now().isoformat())

    async def shutdown(self, wait: bool = False) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
