"""Management contracts, using only fake collectors and temporary persistence."""
import asyncio
import json
import threading
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.scheduler.manager import SchedulerManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    instance = SchedulerManager(state_dir=tmp_path)
    monkeypatch.setattr(instance.scheduler, "start", Mock())
    instance.start(None)
    return instance


@pytest.fixture
def client(manager):
    from src.scheduler.routes import router
    app = FastAPI()
    app.state.scheduler = manager
    app.include_router(router, prefix="/api/funds")
    return TestClient(app)


def test_list_and_pause_persist_across_restart(client, manager, tmp_path, monkeypatch):
    job = client.get("/api/funds/scheduler/jobs").json()["jobs"][0]
    assert job["enabled"] is True
    assert job["running"] is False
    assert job["last_run"] is None
    assert job["cron_human"] == "每周六 07:05（北京时间）"
    response = client.patch("/api/funds/scheduler/jobs/weekly_fund_refresh", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    second = SchedulerManager(state_dir=tmp_path)
    monkeypatch.setattr(second.scheduler, "start", Mock())
    second.start(None)
    assert second.list_jobs()[0]["enabled"] is False
    assert second.list_jobs()[0]["next_run_time"] is None
    assert client.patch("/api/funds/scheduler/jobs/weekly_fund_refresh", json={"enabled": True}).json()["enabled"] is True


def test_write_failure_keeps_enabled_state(client, manager, monkeypatch):
    monkeypatch.setattr(manager, "_save_settings", Mock(side_effect=OSError("disk full")))
    response = client.patch("/api/funds/scheduler/jobs/weekly_fund_refresh", json={"enabled": False})
    assert response.status_code == 503
    assert manager.list_jobs()[0]["enabled"] is True


def test_history_accepts_legacy_and_skips_corrupt_lines(client, manager):
    manager.history_path.write_text(
        json.dumps({"status": "success", "start": "2026-10-24T07:05:00+08:00", "items": []}) +
        '\ninvalid\n' + json.dumps({"status": "partial", "start": "2026-10-25T07:05:00+08:00", "items": []}) + '\n',
        encoding="utf-8",
    )
    response = client.get("/api/funds/scheduler/jobs/weekly_fund_refresh/runs?limit=1")
    assert response.status_code == 200
    assert response.json()["runs"][0]["status"] == "partial"
    assert client.get("/api/funds/scheduler/jobs").json()["jobs"][0]["last_run"]["status"] == "partial"


def test_unknown_job_and_invalid_limit(client):
    assert client.patch("/api/funds/scheduler/jobs/missing", json={"enabled": False}).status_code == 404
    assert client.post("/api/funds/scheduler/jobs/missing/run").status_code == 404
    assert client.get("/api/funds/scheduler/jobs/missing/runs").status_code == 404
    assert client.get("/api/funds/scheduler/jobs/weekly_fund_refresh/runs?limit=0").status_code == 422


def test_manual_and_scheduled_runs_share_reservation(tmp_path, monkeypatch):
    from src.scheduler import weekly_refresh
    release = threading.Event()
    calls = []

    def fake_refresh(**kwargs):
        calls.append(kwargs)
        kwargs["on_progress"]({"status": "running", "items": [{"tab": "bond", "status": "running"}]})
        assert release.wait(5)
        return {"status": "success", "items": []}

    monkeypatch.setattr(weekly_refresh, "refresh_weekly_sync", fake_refresh)

    async def scenario():
        instance = SchedulerManager(state_dir=tmp_path)
        instance.start(None)
        try:
            response = await instance.trigger_now("weekly_fund_refresh")
            assert response["status"] == "running"
            assert instance.list_jobs()[0]["running"] is True
            with pytest.raises(ValueError, match="运行"):
                await instance.trigger_now("weekly_fund_refresh")
            await instance._weekly_refresh()
            assert len(instance._background_tasks) == 1
            instance.set_enabled("weekly_fund_refresh", False)
            assert instance.list_jobs()[0]["running"] is True
        finally:
            release.set()
            await asyncio.gather(*instance._background_tasks)
            await instance.shutdown()
            await asyncio.sleep(0)
        assert len(calls) == 1
        assert instance.list_jobs()[0]["running"] is False

    asyncio.run(scenario(), loop_factory=asyncio.SelectorEventLoop)


def test_run_endpoint_returns_conflict(client, manager, monkeypatch):
    async def conflict(job_id):
        raise ValueError("任务正在运行")
    monkeypatch.setattr(manager, "trigger_now", conflict)
    assert client.post("/api/funds/scheduler/jobs/weekly_fund_refresh/run").status_code == 409


def test_worker_exception_releases_reservation_and_is_visible(tmp_path, monkeypatch):
    from src.scheduler import weekly_refresh
    monkeypatch.setattr(weekly_refresh, "refresh_weekly_sync", Mock(side_effect=OSError("history disk full")))

    async def scenario():
        instance = SchedulerManager(state_dir=tmp_path)
        monkeypatch.setattr(instance.scheduler, "start", Mock())
        instance.start(None)
        await instance._weekly_refresh()
        job = instance.list_jobs()[0]
        assert job["running"] is False
        assert job["last_run"]["status"] == "failed"
        assert job["last_run"]["error"] == "history disk full"
        await instance.trigger_now("weekly_fund_refresh")
        await asyncio.gather(*instance._background_tasks)
        assert instance.list_jobs()[0]["running"] is False

    asyncio.run(scenario(), loop_factory=asyncio.SelectorEventLoop)
