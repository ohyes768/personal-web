"""Web owns daily collection; report scheduling and delivery are retired."""
from __future__ import annotations

import asyncio
import importlib
import sys
import threading
import time
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import router
from src.services import scheduler as scheduler_module
from src.core.indexes import index_codes, trend_index_codes
from src.services.store import Store


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/report-settings"),
    ("PATCH", "/api/report-settings"),
    ("POST", "/api/report-jobs/weekly_report/run"),
    ("POST", "/api/report-jobs/daily_refresh/run"),
])
def test_report_control_endpoints_are_removed(method, path):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.request(method, path).status_code == 404


def test_daily_scheduler_registers_only_refresh_and_runs_it():
    async def scenario():
        refresh = AsyncMock(return_value={"success": True})
        scheduler = scheduler_module.RefreshScheduler(refresh, daily_cron="15 17 * * mon-fri")
        scheduler.start()
        try:
            jobs = scheduler._scheduler.get_jobs()
            assert sorted(job.id for job in jobs) == ["daily_refresh"]
            assert str(jobs[0].trigger.timezone) == "Asia/Shanghai"
            assert str(jobs[0].trigger.fields[-2]) == "15"
            await jobs[0].func()
            refresh.assert_awaited_once()
        finally:
            await scheduler.shutdown()
    asyncio.run(scenario())


@pytest.mark.parametrize("timeout", [0.01, 1.0])
def test_shutdown_handles_inflight_daily_refresh(timeout):
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()

        async def refresh():
            started.set()
            await finish.wait()

        scheduler = scheduler_module.RefreshScheduler(refresh)
        scheduler.start()
        running = asyncio.create_task(scheduler._run_daily())
        await started.wait()
        if timeout == 1.0:
            asyncio.get_running_loop().call_later(0.01, finish.set)
        await scheduler.shutdown(timeout=timeout)
        await asyncio.gather(running, return_exceptions=True)
        assert not scheduler._tasks
        assert running.cancelled() == (timeout == 0.01)
        await scheduler._run_daily()  # closing scheduler must not start work again
        assert not scheduler._tasks
    asyncio.run(scenario())


@pytest.fixture()
def main_module(monkeypatch, tmp_path):
    monkeypatch.setenv("INDEX_TRENDS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INDEX_TRENDS_LIXINGER_TOKEN", "")
    first_import = "src.main" not in sys.modules
    main = importlib.import_module("src.main")
    if first_import:
        # Close the module-level app's store before making per-test applications.
        with TestClient(main.app):
            pass
    return main


@pytest.mark.parametrize("market_error", [False, True])
@pytest.mark.parametrize("valuation_error", [False, True])
def test_application_keeps_daily_market_and_valuation_refresh(main_module, monkeypatch, market_error, valuation_error):
    market = AsyncMock(side_effect=RuntimeError("market unavailable") if market_error else None)
    valuation_done = threading.Event()

    def collect_valuation(**kwargs):
        valuation_done.set()
        if valuation_error:
            raise RuntimeError("valuation unavailable")

    valuation = Mock(side_effect=collect_valuation)
    monkeypatch.setattr(main_module.WeeklyTrendService, "refresh", market)
    monkeypatch.setattr(main_module.ValuationService, "refresh", valuation)
    monkeypatch.setattr(main_module.ValuationService, "refresh_scheduled", valuation)
    with TestClient(main_module.create_app()) as client:
        assert valuation_done.wait(2)  # startup valuation initialization stays enabled
        # 启动采集按指数逐个执行：等它全部走完再重置计数，
        # 否则后台任务的第二次调用会落进下面的"不该被调用"断言里（竞态）。
        deadline = time.time() + 2
        while valuation.call_count < len(index_codes()) and time.time() < deadline:
            time.sleep(0.005)
        valuation.reset_mock()
        scheduler = client.app.state.scheduler
        # 行情与估值是两个独立任务：行情失败不影响估值采集
        assert sorted(job["id"] for job in scheduler.jobs_info()) == ["daily_refresh", "valuation_refresh"]
        client.portal.call(scheduler._run_daily)
        # 行情现在按指数逐个刷新：每个注册指数一次
        # 行情只遍历有通道的指数（创业板50 只有估值，不抓K线）
        assert market.await_count == len(trend_index_codes())
        valuation.assert_not_called()  # 16:30 只刷行情，不联动估值
        client.portal.call(scheduler._run_valuation)
        assert valuation.call_count == len(index_codes())
        assert client.get("/api/reports").json()["reports"] == []


def test_startup_preserves_historical_reports_without_refresh_or_delivery(main_module, monkeypatch, tmp_path):
    database = tmp_path / "history.db"
    store = Store(database)
    store.upsert_report({
        "idempotency_key": "000300|2026-W43|weekly", "index_code": "000300",
        "iso_week": "2026-W43", "model_id": "legacy-model", "model_kind": "trailing_120m",
        "content": "历史报告", "status": "failed", "snapshot_json": '{"legacy":true}',
    })
    before = store.list_reports()
    settings = store.get_report_settings()
    market = AsyncMock()
    monkeypatch.setattr(main_module, "Store", lambda _: store)
    monkeypatch.setattr(main_module.WeeklyTrendService, "refresh", market)
    monkeypatch.setattr(main_module.WeeklyTrendService, "refresh_sync", Mock(side_effect=AssertionError("no catchup")))
    monkeypatch.setattr(main_module.ValuationService, "refresh", Mock())
    with TestClient(main_module.create_app()) as client:
        assert client.get("/api/reports").json()["reports"] == before
        assert store.get_report_settings() == settings
        market.assert_not_awaited()
    reopened = Store(database)
    try:
        assert reopened.list_reports() == before
        assert reopened.get_report_settings() == settings
    finally:
        reopened.close()
