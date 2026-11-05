"""每日估值采集任务：与行情刷新独立、休市跳过、日历异常明确报错（脱网）。"""
from __future__ import annotations

import asyncio
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.data import lixinger as lx
from src.data.trading_calendar import CalendarUnavailableError, StaticTradingCalendar
from src.services.scheduler import JOB_DAILY, JOB_VALUATION, RefreshScheduler
from src.services.store import Store
from src.services.valuation_service import ValuationService

TZ = ZoneInfo("Asia/Shanghai")

# 18:30 采集时刻
COLLECT_TIME = datetime(2026, 10, 30, 18, 30, tzinfo=TZ)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload=None, error: Exception | None = None, delay: float = 0.0):
        self.payload = payload
        self.error = error
        self.delay = delay
        self.calls = 0
        self._lock = threading.Lock()

    def post(self, url, json=None):
        with self._lock:
            self.calls += 1
        if self.delay:
            import time

            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.payload)

    def close(self):
        return None


def _payload(day="2026-10-30T15:00:00+08:00", pe=12.3456, ratio=0.565952) -> dict:
    return {
        "code": 1,
        "data": [
            {
                "stockCode": "000300",
                "date": day,
                lx.METRIC_PE_TTM: pe,
                lx.METRIC_CVPOS: ratio,
            }
        ],
    }


def _week_sessions(week_start: str) -> list[str]:
    start = date.fromisoformat(week_start)
    return [(start + timedelta(days=i)).isoformat() for i in range(5)]


def _calendar(*days: str) -> StaticTradingCalendar:
    sessions = [date.fromisoformat(d) for d in days]
    return StaticTradingCalendar(
        sessions,
        coverage_start=sessions[0] - timedelta(days=120),
        coverage_end=sessions[-1] + timedelta(days=30),
    )


def _valuation(store, client, now=COLLECT_TIME, calendar=None, token="token"):
    return ValuationService(
        store,
        token=token,
        calendar=calendar or _calendar(*_week_sessions("2026-10-26")),
        now_fn=lambda: now,
        client_factory=lambda: client,
    )


@pytest.fixture()
def store(tmp_path) -> Store:
    return Store(tmp_path / "valuation.db")


# ---- 调度器：两个独立任务 ----
def test_scheduler_registers_daily_and_valuation_jobs():
    async def refresh():
        return None

    async def valuation():
        return None

    async def scenario() -> list[str]:
        scheduler = RefreshScheduler(
            refresh_fn=refresh,
            daily_cron="30 16 * * mon-fri",
            valuation_fn=valuation,
            valuation_cron="30 18 * * mon-fri",
        )
        scheduler.start()
        try:
            return [job["id"] for job in scheduler.jobs_info()]
        finally:
            await scheduler.shutdown()

    assert asyncio.run(scenario()) == [JOB_DAILY, JOB_VALUATION]


def test_scheduler_without_valuation_callback_registers_only_daily():
    async def refresh():
        return None

    async def scenario() -> list[str]:
        scheduler = RefreshScheduler(refresh_fn=refresh)
        scheduler.start()
        try:
            return [job["id"] for job in scheduler.jobs_info()]
        finally:
            await scheduler.shutdown()

    assert asyncio.run(scenario()) == [JOB_DAILY]


def test_scheduler_valuation_cron_is_configurable():
    async def refresh():
        return None

    async def valuation():
        return None

    async def scenario() -> str:
        scheduler = RefreshScheduler(
            refresh_fn=refresh,
            valuation_fn=valuation,
            valuation_cron="45 19 * * mon-fri",
        )
        scheduler.start()
        try:
            job = next(j for j in scheduler._scheduler.get_jobs() if j.id == JOB_VALUATION)
            return str(job.trigger)
        finally:
            await scheduler.shutdown()

    trigger = asyncio.run(scenario())
    assert "hour='19'" in trigger
    assert "minute='45'" in trigger
    assert "day_of_week='mon-fri'" in trigger


def test_scheduler_shutdown_is_idempotent():
    async def refresh():
        return None

    async def scenario() -> None:
        scheduler = RefreshScheduler(refresh_fn=refresh)
        await scheduler.shutdown()
        await scheduler.shutdown()

    asyncio.run(scenario())


# ---- 估值采集任务：休市跳过与日历异常 ----
def test_scheduled_collection_skips_on_holiday_without_request(store):
    client = _FakeClient(_payload())
    # 2026-11-02 休市：日历确认当日不是交易日
    calendar = _calendar(
        "2026-10-30",
        "2026-11-03",
        "2026-11-04",
        "2026-11-05",
        "2026-11-06",
    )
    service = _valuation(
        store,
        client,
        now=datetime(2026, 11, 2, 18, 30, tzinfo=TZ),
        calendar=calendar,
    )
    result = service.refresh_scheduled()
    assert result["skipped"] is True
    assert result["reason"] == "not_trading_day"
    assert client.calls == 0


def test_scheduled_collection_skips_on_weekend_without_request(store):
    client = _FakeClient(_payload())
    service = _valuation(
        store,
        client,
        now=datetime(2026, 11, 1, 18, 30, tzinfo=TZ),
    )
    result = service.refresh_scheduled()
    assert result["skipped"] is True
    assert client.calls == 0


def test_scheduled_collection_raises_when_calendar_unavailable(store):
    client = _FakeClient(_payload())
    narrow = StaticTradingCalendar(
        [date.fromisoformat(d) for d in _week_sessions("2026-10-26")],
        coverage_start=date(2026, 10, 26),
        coverage_end=date(2026, 10, 30),
    )
    service = _valuation(
        store,
        client,
        now=datetime(2026, 11, 6, 18, 30, tzinfo=TZ),
        calendar=narrow,
    )
    with pytest.raises(CalendarUnavailableError):
        service.refresh_scheduled()
    assert client.calls == 0


def test_scheduled_collection_publishes_daily_target(store):
    client = _FakeClient(_payload())
    service = _valuation(store, client)
    result = service.refresh_scheduled()
    assert result["state"] == "ok"
    assert result["target_date"] == "2026-10-30"
    assert result["as_of"] == "2026-10-30"
    assert client.calls == 1


def test_scheduled_collection_reuses_cache_for_same_target(store):
    client = _FakeClient(_payload())
    service = _valuation(store, client)
    service.refresh_scheduled()
    service.refresh_scheduled()
    assert client.calls == 1


def test_scheduled_collection_retries_after_failure(store):
    failing = _FakeClient(error=lx.LixingerError("network_error", "理杏仁请求失败"))
    service = _valuation(store, failing)
    assert service.refresh_scheduled()["state"] == "error"
    # 冷却窗口内不重复请求
    assert service.refresh_scheduled()["state"] == "error"
    assert failing.calls == 1
    # 冷却过后允许重试
    service._now_fn = lambda: datetime(2026, 10, 30, 19, 0, tzinfo=TZ)
    assert service.refresh_scheduled()["state"] == "error"
    assert failing.calls == 2


# ---- 并发保护 ----
def test_overlapping_collection_only_requests_once(store):
    client = _FakeClient(_payload(), delay=0.05)
    service = _valuation(store, client)
    results: list[dict] = []
    barrier = threading.Barrier(3)

    def worker() -> None:
        barrier.wait()
        results.append(service.refresh_scheduled())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    barrier.wait()
    for t in threads:
        t.join()
    # 并发执行不能重复请求供应商
    assert client.calls == 1
    assert all(r["state"] == "ok" for r in results)


# ---- 应用装配：16:30 只刷行情，估值独立成任务 ----
def test_application_separates_market_and_valuation_jobs():
    from src import main as main_module

    market_calls: list[str] = []
    valuation_calls: list[str] = []

    async def market():
        market_calls.append("market")

    async def valuation():
        valuation_calls.append("valuation")

    jobs = main_module.build_jobs(market, valuation)
    assert set(jobs) == {JOB_DAILY, JOB_VALUATION}
    asyncio.run(jobs[JOB_DAILY]())
    assert market_calls == ["market"]
    assert valuation_calls == []  # 16:30 行情任务不联动估值
    asyncio.run(jobs[JOB_VALUATION]())
    assert valuation_calls == ["valuation"]
