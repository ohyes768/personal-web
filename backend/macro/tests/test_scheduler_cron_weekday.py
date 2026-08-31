"""预设 cron 必须在周一触发（APScheduler 3.x 的 dow 数字 0=周一，不是 crontab 的周日）。

回归：`1-5` 会被解析成周二到周六，周一的 16:30 / 07:30 整组跳过，
看起来像定时任务没生效。预设必须用 mon-fri（或 0-4）。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from apscheduler.triggers.cron import CronTrigger

from src.scheduler.cron_human import cron_to_human

_SCHEDULER_JSON = Path(__file__).resolve().parents[1] / "src" / "scheduler" / "scheduler.json"
_SHANGHAI = ZoneInfo("Asia/Shanghai")
# 2026-08-31 是周一（与线上复现日一致）。用 00:00：07:30 与 16:30 当天都还没到。
_MONDAY_START = datetime(2026, 8, 31, 0, 0, tzinfo=_SHANGHAI)


@pytest.mark.unit
def test_preset_crons_fire_on_monday():
    """scheduler.json 每个工作日任务：周一中午算下次，必须落在当天而不是周二。"""
    config = json.loads(_SCHEDULER_JSON.read_text(encoding="utf-8"))
    jobs = [j for j in config["jobs"] if "1-5" in j["cron"] or "mon-fri" in j["cron"] or "0-4" in j["cron"]]
    assert jobs, "scheduler.json 应有工作日 cron 任务"
    for job in jobs:
        trigger = CronTrigger.from_crontab(job["cron"], timezone="Asia/Shanghai")
        nxt = trigger.get_next_fire_time(None, _MONDAY_START)
        assert nxt is not None, f"{job['id']} 无下次触发"
        assert nxt.date() == _MONDAY_START.date(), (
            f"{job['id']} cron={job['cron']!r} 周一被跳过，下次={nxt.isoformat()}。"
            "APScheduler dow 数字 0=周一：不要用 crontab 习惯的 1-5，改用 mon-fri。"
        )


@pytest.mark.unit
def test_preset_cron_human_says_weekday():
    """UI 文案仍应是「周一至周五」，不能把 mon-fri 原样丢给前端。"""
    config = json.loads(_SCHEDULER_JSON.read_text(encoding="utf-8"))
    for job in config["jobs"]:
        if job["id"] in ("a_share_daily", "global_daily"):
            human = cron_to_human(job["cron"])
            assert "周一至周五" in human, f"{job['id']} cron_human={human!r}"
