"""Weekly scheduling and orchestration, without external data collection."""
import asyncio
import json
import threading
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from src.scheduler.manager import SchedulerManager


def test_only_weekly_job_registered(monkeypatch):
    manager = SchedulerManager()
    monkeypatch.setattr(manager.scheduler, "start", Mock())
    manager.start(None)
    jobs = manager.scheduler.get_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "weekly_fund_refresh"
    assert job.max_instances == 1
    assert job.coalesce is True
    assert job.misfire_grace_time == 3600
    now = datetime(2026, 10, 29, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert job.trigger.get_next_fire_time(None, now).isoformat() == "2026-10-31T07:05:00+08:00"


def test_weekly_order_parameters_and_history(monkeypatch, tmp_path):
    from src.scheduler import weekly_refresh as weekly
    from src.data.market_subtype_map import DISCOVERY_BOND_SUBTYPES, DISCOVERY_STOCK_SUBTYPES
    calls = []

    def configured(**kwargs):
        calls.append(("bond", kwargs))
        return {"completed": 2, "failed": 0}

    def stock(**kwargs):
        calls.append(("stock", kwargs))
        return {"completed": 3, "failed": 0}

    def market(**kwargs):
        calls.append(("market", kwargs))
        return {"stage_results": {"L0": {"status": "done", "result": {"failed": 0}}}}

    monkeypatch.setattr(weekly, "refresh_configured_funds_sync", configured)
    monkeypatch.setattr(weekly, "refresh_stock_funds_sync", stock)
    monkeypatch.setattr(weekly, "refresh_market_full_sync", market)
    path = tmp_path / "scheduler" / "weekly.jsonl"
    result = weekly.refresh_weekly_sync(history_path=path)
    assert [c[0] for c in calls] == ["bond", "stock", "market", "market"]
    assert calls[0][1] == calls[1][1] == {"use_cache": False}
    for call, profile, subtypes, ret in (
        (calls[2], "bond", DISCOVERY_BOND_SUBTYPES, 10),
        (calls[3], "stock", DISCOVERY_STOCK_SUBTYPES, 20),
    ):
        assert call[1] == dict(pipeline_profile=profile, universe_filter=list(subtypes),
                              min_ret_3y=ret, min_size_yi=5, min_mgr_exp=5)
    assert result["status"] == "success"
    assert [i["tab"] for i in result["items"]] == ["bond", "stock", "discovery-bond", "discovery-stock"]
    assert result["start"].endswith("+08:00")
    assert all(i["end"].endswith("+08:00") for i in result["items"])
    assert json.loads(path.read_text(encoding="utf-8")) == result
    weekly.refresh_weekly_sync(history_path=path)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_failure_does_not_stop_later_tabs(monkeypatch, tmp_path):
    from src.scheduler import weekly_refresh as weekly
    monkeypatch.setattr(weekly, "refresh_configured_funds_sync", Mock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(weekly, "refresh_stock_funds_sync", Mock(return_value={"completed": 2, "failed": 1}))
    market = Mock(return_value={"stage_results": {"L0": {"status": "done", "result": {"failed": 0}}}})
    monkeypatch.setattr(weekly, "refresh_market_full_sync", market)
    result = weekly.refresh_weekly_sync(history_path=tmp_path / "history.jsonl")
    assert market.call_count == 2
    assert result["status"] == "partial"
    assert [i["status"] for i in result["items"]] == ["failed", "partial", "success", "success"]
    assert result["items"][0]["error"] == "offline"


@pytest.mark.parametrize("result,expected", [
    ({"completed": 0, "failed": 3}, "failed"),
    ({"total": 0, "completed": 0, "failed": 0}, "failed"),
    ({"stage_results": {"L1": {"status": "done", "result": {"failed": 2, "inserted": 3, "updated": 1, "total": 6}}}}, "partial"),
    ({"stage_results": {"L1": {"status": "done", "result": {"failed": 2, "completed": 3}}}}, "partial"),
    ({"stage_results": {"L1": {"status": "error"}}}, "failed"),
    ({"stage_results": {"L0": {"status": "done"}, "L1": {"status": "error"}}}, "partial"),
])
def test_result_classification(result, expected):
    from src.scheduler.weekly_refresh import classify_result
    assert classify_result(result) == expected


def test_scheduler_offloads_blocking_work(monkeypatch):
    from src.scheduler import weekly_refresh as weekly
    caller_thread = threading.get_ident()
    worker_threads = []

    def refresh(**kwargs):
        worker_threads.append(threading.get_ident())
        return {"status": "success"}

    run = Mock(side_effect=refresh)
    monkeypatch.setattr(weekly, "refresh_weekly_sync", run)
    # No socket IO here; avoid Windows Proactor handle initialization in the sandbox.
    asyncio.run(SchedulerManager()._weekly_refresh(), loop_factory=asyncio.SelectorEventLoop)
    run.assert_called_once()
    assert run.call_args.kwargs["trigger"] == "scheduled"
    assert worker_threads[0] != caller_thread


def test_all_tabs_failure_is_recorded(monkeypatch, tmp_path):
    from src.scheduler import weekly_refresh as weekly
    for name in ("refresh_configured_funds_sync", "refresh_stock_funds_sync", "refresh_market_full_sync"):
        monkeypatch.setattr(weekly, name, Mock(side_effect=RuntimeError("offline")))
    path = tmp_path / "history.jsonl"
    record = weekly.refresh_weekly_sync(history_path=path)
    assert record["status"] == "failed"
    assert len(record["items"]) == 4
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "failed"
