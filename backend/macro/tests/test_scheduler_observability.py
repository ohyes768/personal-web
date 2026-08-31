"""scheduler 排查可观测性：启动 dump / 错过触发 / 运行时状态"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED

from src.scheduler.manager import SchedulerManager
from tests.test_scheduler_manager import make_manager

BEIJING = timezone(timedelta(hours=8))


@pytest.mark.unit
def test_log_schedule_dump_includes_next_run(tmp_path, caplog):
    """启动 dump 必须带每个 job 的 next_run，否则周一被跳过时日志看不出来。"""
    mgr = make_manager(tmp_path)
    nxt = datetime(2026, 9, 1, 16, 30, tzinfo=BEIJING)
    fake_job = SimpleNamespace(next_run_time=nxt)
    mgr._scheduler = MagicMock()
    mgr._scheduler.get_job.return_value = fake_job

    with caplog.at_level(logging.INFO):
        mgr._log_schedule_dump()

    assert "a_share_daily" in caplog.text
    assert "next_run=" in caplog.text
    assert "2026-09-01" in caplog.text
    assert str(tmp_path / "history.jsonl") in caplog.text or "history.jsonl" in caplog.text


@pytest.mark.unit
def test_missed_event_logs_warning(tmp_path, caplog):
    mgr = make_manager(tmp_path)
    event = SimpleNamespace(
        code=EVENT_JOB_MISSED,
        job_id="a_share_daily",
        scheduled_run_time=datetime(2026, 8, 31, 16, 30, tzinfo=BEIJING),
        exception=None,
    )
    with caplog.at_level(logging.WARNING):
        mgr._on_scheduler_event(event)
    assert "a_share_daily" in caplog.text
    assert "错过" in caplog.text


@pytest.mark.unit
def test_error_and_max_instances_events_log(tmp_path, caplog):
    mgr = make_manager(tmp_path)
    with caplog.at_level(logging.WARNING):
        mgr._on_scheduler_event(
            SimpleNamespace(
                code=EVENT_JOB_ERROR,
                job_id="global_daily",
                scheduled_run_time=None,
                exception=RuntimeError("boom"),
            )
        )
        mgr._on_scheduler_event(
            SimpleNamespace(code=EVENT_JOB_MAX_INSTANCES, job_id="a_share_daily")
        )
    assert "global_daily" in caplog.text
    assert "max_instances" in caplog.text or "尚未结束" in caplog.text


@pytest.mark.unit
def test_get_status_includes_runtime_paths(tmp_path):
    mgr = make_manager(tmp_path)
    status = mgr.get_status()
    assert status["timezone"] == "Asia/Shanghai"
    assert status["port"] == 18094
    assert status["running"] is False
    assert str(tmp_path / "history.jsonl") == status["history_path"]
    assert status["history_exists"] is True
    ids = {j["id"] for j in status["jobs"]}
    assert "a_share_daily" in ids


def _reset_logger(name: str) -> None:
    log = logging.getLogger(name)
    for handler in list(log.handlers):
        log.removeHandler(handler)
        handler.close()


@pytest.mark.unit
def test_scheduler_logger_also_writes_service_log(tmp_path):
    """业务调度日志必须同时进 service.log 与 scheduler.log，旧排查习惯不断档。"""
    from src.utils.logger import setup_logger

    _reset_logger("scheduler")
    _reset_logger("apscheduler")
    try:
        log = setup_logger("scheduler", log_dir=str(tmp_path))
        log.info("hello-scheduler-dual-write")
        logging.getLogger("apscheduler").info("hello-apscheduler-dual-write")
        for handler in logging.getLogger("scheduler").handlers:
            handler.flush()
        for handler in logging.getLogger("apscheduler").handlers:
            handler.flush()

        service = (tmp_path / "service.log").read_text(encoding="utf-8")
        dedicated = (tmp_path / "scheduler.log").read_text(encoding="utf-8")
        assert "hello-scheduler-dual-write" in service
        assert "hello-scheduler-dual-write" in dedicated
        assert "hello-apscheduler-dual-write" in service
        assert "hello-apscheduler-dual-write" in dedicated
    finally:
        _reset_logger("scheduler")
        _reset_logger("apscheduler")
