"""scheduler 时间戳必须带北京时区偏移（+08:00）

容器默认 UTC 时 datetime.now().isoformat() 会写成 naive UTC（如 08:30），
前端再当本地时间显示，就会比北京时间慢 8 小时。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.scheduler.jobs import run_group
from src.scheduler.manager import SchedulerManager
from src.scheduler.timezone import now_shanghai, now_shanghai_iso
from tests.test_scheduler_jobs import FakeCtx, spec

BEIJING = timezone(timedelta(hours=8))


@pytest.mark.unit
def test_now_shanghai_iso_has_plus_08_offset():
    """now_shanghai_iso() 必须带 +08:00，且能 roundtrip 成 UTC+8"""
    iso = now_shanghai_iso()
    dt = datetime.fromisoformat(iso)
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(hours=8)
    assert abs((dt - now_shanghai()).total_seconds()) < 1


@pytest.mark.unit
def test_skipped_run_timestamps_are_beijing():
    """非交易日 skip 的 start/end 必须是带 +08:00 的 ISO"""
    ctx = FakeCtx({"test_job": spec(["/update/vix"], check_trading_day=True)})
    with patch("src.scheduler.jobs.is_trading_day", return_value=False):
        result = asyncio.run(run_group(ctx, "test_job"))
    assert result["status"] == "skipped"
    for key in ("start", "end"):
        dt = datetime.fromisoformat(result[key])
        assert dt.tzinfo is not None, f"{key} 缺少时区: {result[key]}"
        assert dt.utcoffset() == timedelta(hours=8)


@pytest.mark.unit
def test_run_job_wrapper_exception_timestamps_are_beijing(tmp_path: Path):
    """unhandled 异常落盘的 start/end 也必须带 +08:00"""
    mgr = SchedulerManager(
        port=18094,
        config_path=tmp_path / "scheduler.json",
        history_path=tmp_path / "history.jsonl",
    )
    mgr.jobs_meta = {
        "a_share_daily": {
            "id": "a_share_daily",
            "target": "run_group",
            "cron": "30 16 * * 1-5",
        }
    }

    async def boom(ctx, job_id):
        raise RuntimeError("akshare 挂了")

    with patch("src.scheduler.manager.JOB_TARGETS", {"run_group": boom}):
        asyncio.run(mgr._run_job_wrapper("a_share_daily"))

    rec = mgr.get_job_runs("a_share_daily")[0]
    for key in ("start", "end"):
        dt = datetime.fromisoformat(rec[key])
        assert dt.tzinfo is not None, f"{key} 缺少时区: {rec[key]}"
        assert dt.utcoffset() == timedelta(hours=8)
