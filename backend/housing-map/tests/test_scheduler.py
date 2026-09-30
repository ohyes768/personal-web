"""scheduler 模块测试: cron 周一触发 + 409 互斥不抛 + 启停幂等"""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from apscheduler.triggers.cron import CronTrigger

from src import scheduler
from src.scheduler import (
    JOB_ID,
    REFRESH_CRON,
    run_weekly_refresh,
    shutdown_scheduler,
    start_scheduler,
)


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """清掉模块级单例，避免失败用例残留影响后续用例。"""
    yield
    scheduler._scheduler = None

_SHANGHAI = ZoneInfo("Asia/Shanghai")
# 2026-09-28 是周一 00:00（本周刷新还没到点）
_MONDAY_START = datetime(2026, 9, 28, 0, 0, tzinfo=_SHANGHAI)
# 2026-09-27 是周日 20:00（最近一次触发点是第二天周一）
_SUNDAY_EVE = datetime(2026, 9, 27, 20, 0, tzinfo=_SHANGHAI)


def test_cron_fires_monday_2117():
    # 从周一 00:00 算下次触发，必须落在当天 21:17 而不是周二
    # （dow 若误写数字会被当成 crontab 习惯，周一直接被跳过）
    trigger = CronTrigger.from_crontab(REFRESH_CRON, timezone="Asia/Shanghai")
    nxt = trigger.get_next_fire_time(None, _MONDAY_START)
    assert nxt == datetime(2026, 9, 28, 21, 17, tzinfo=_SHANGHAI)


def test_cron_from_sunday_fires_next_monday():
    # 周日晚上算下次，落在周一（mon 无数字歧义）
    trigger = CronTrigger.from_crontab(REFRESH_CRON, timezone="Asia/Shanghai")
    nxt = trigger.get_next_fire_time(None, _SUNDAY_EVE)
    assert nxt.date() == _SUNDAY_EVE.date() + timedelta(days=1)


def test_run_weekly_refresh_skips_when_busy(monkeypatch):
    # 已有刷新在跑 (409): 只记日志，不抛异常（抛了会被 APScheduler 记为 job error）
    async def fake_start(limit):
        return False, 409, {"success": False, "error": "已有刷新任务在运行"}

    monkeypatch.setattr(scheduler.refresh_service, "start_refresh", fake_start)
    asyncio.run(run_weekly_refresh())  # 不抛即通过


def test_run_weekly_refresh_swallows_start_failure(monkeypatch):
    # 启动失败 (500): 记 error 日志但不抛，避免下一轮 misfire 噪音
    async def fake_start(limit):
        return False, 500, {"success": False, "error": "小区清单为空"}

    monkeypatch.setattr(scheduler.refresh_service, "start_refresh", fake_start)
    asyncio.run(run_weekly_refresh())


def test_run_weekly_refresh_starts_job(monkeypatch):
    called = []

    async def fake_start(limit):
        called.append(limit)
        return True, 200, {"success": True, "data": {"total": 3}}

    monkeypatch.setattr(scheduler.refresh_service, "start_refresh", fake_start)
    asyncio.run(run_weekly_refresh())
    assert called == [0]  # 0 = 全量


def test_start_scheduler_idempotent():
    # AsyncIOScheduler 的 start/shutdown 都要在运行中的事件循环里（生产在 lifespan 内）
    async def scenario():
        start_scheduler()
        assert scheduler._scheduler is not None
        jobs = scheduler._scheduler.get_jobs()
        assert any(job.id == JOB_ID for job in jobs)
        start_scheduler()  # 第二次调用: 只记警告，不新建
        assert scheduler._scheduler is not None
        shutdown_scheduler()
        assert scheduler._scheduler is None

    asyncio.run(scenario())


def test_shutdown_scheduler_idempotent():
    shutdown_scheduler()  # 未启动时静默
    assert scheduler._scheduler is None
