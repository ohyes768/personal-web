"""周报中的估值：正常展示、失败不阻断投递、快照固化、休市沿用。"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from src.data import lixinger as lx
from src.data.provider import KlineBar
from src.data.trading_calendar import StaticTradingCalendar
from src.services.report_service import ReportService
from src.services.trend_service import SHANGHAI_TZ, WeeklyTrendService
from src.services.valuation_service import ValuationService

from tests.conftest import FRIDAY_CLOSE


class FakeNotifier:
    def __init__(self, configured: bool = True):
        self.configured = configured
        self.calls: list[tuple[str, str]] = []

    def send_markdown(self, title: str, text: str) -> tuple[bool, str | None]:
        self.calls.append((title, text))
        if not self.configured:
            return False, "channel_not_configured"
        return True, None


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload=None, error: Exception | None = None):
        self.payload = payload
        self.error = error
        self.calls = 0

    def post(self, url, json=None):
        self.calls += 1
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


def _valuation(store, service, client, token="token") -> ValuationService:
    return ValuationService(
        store,
        token=token,
        calendar=service.trading_calendar,
        now_fn=lambda: FRIDAY_CLOSE,
        client_factory=lambda: client,
    )


def _stub(monkeypatch, service, result=None):
    from src.services.trend_service import WeeklyRefreshResult

    payload = result or WeeklyRefreshResult(success=True, message="stub", data_cutoff_week="2026-10-26")
    monkeypatch.setattr(service, "refresh_sync", lambda client=None: payload)


def test_report_shows_valuation_line_and_snapshot(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    client = _FakeClient(_payload())
    valuation = _valuation(store, service, client)
    notifier = FakeNotifier()
    report = ReportService(
        store, service, notifier, now_fn=lambda: FRIDAY_CLOSE, valuation_service=valuation
    )
    outcome = report.run_weekly_sync(manual=True)
    assert outcome["business_status"] == "normal"
    text = notifier.calls[0][1]
    assert "PE-TTM 近10年分位" in text
    assert "56.6%" in text
    assert "12.35" in text
    assert "2026-10-30" in text
    assert "理杏仁" in text
    # 通道位置与估值分位是两件事，文案不能混
    assert "通道位置：" in text


def test_report_snapshot_freezes_valuation(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    client = _FakeClient(_payload())
    valuation = _valuation(store, service, client)
    notifier = FakeNotifier()
    ReportService(
        store, service, notifier, now_fn=lambda: FRIDAY_CLOSE, valuation_service=valuation
    ).run_weekly_sync(manual=True)
    saved = store.list_reports(limit=1)[0]
    snapshot = json.loads(saved["snapshot_json"])
    assert snapshot["valuation"]["state"] == "ok"
    assert snapshot["valuation"]["percentile_pct"] == 56.6
    assert snapshot["valuation"]["as_of"] == "2026-10-30"


def test_valuation_failure_does_not_block_report(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    client = _FakeClient(error=lx.LixingerError("network_error", "理杏仁请求失败"))
    valuation = _valuation(store, service, client)
    notifier = FakeNotifier()
    outcome = ReportService(
        store, service, notifier, now_fn=lambda: FRIDAY_CLOSE, valuation_service=valuation
    ).run_weekly_sync(manual=True)
    assert outcome["business_status"] == "normal"
    assert outcome["sent"] is True
    text = notifier.calls[0][1]
    assert "估值：暂不可用" in text
    assert "通道位置" in text


def test_disabled_valuation_states_no_token(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    client = _FakeClient(_payload())
    valuation = _valuation(store, service, client, token="")
    notifier = FakeNotifier()
    ReportService(
        store, service, notifier, now_fn=lambda: FRIDAY_CLOSE, valuation_service=valuation
    ).run_weekly_sync(manual=True)
    text = notifier.calls[0][1]
    assert "未配置理杏仁访问令牌" in text
    assert client.calls == 0


def test_no_trading_report_reuses_cached_valuation(store, monkeypatch):
    sessions = [date(2026, 2, 9), date(2026, 2, 10), date(2026, 2, 11), date(2026, 2, 12), date(2026, 2, 13)]
    calendar = StaticTradingCalendar(sessions, date(2026, 2, 1), date(2026, 2, 28))
    now = datetime(2026, 2, 20, 19, 0, tzinfo=SHANGHAI_TZ)
    service = WeeklyTrendService(store, now_fn=lambda: now, calendar=calendar)
    _stub(monkeypatch, service)
    # 先缓存一条更早交易周的估值
    store.publish_valuation(
        "000300",
        lx.VALUATION_SOURCE,
        lx.VALUATION_METRIC,
        lx.VALUATION_WINDOW,
        [("2026-02-13", 11.5, 0.42)],
        "2026-02-13",
    )
    valuation = ValuationService(store, token="token", calendar=calendar, now_fn=lambda: now)
    notifier = FakeNotifier()
    outcome = ReportService(
        store, service, notifier, now_fn=lambda: now, valuation_service=valuation
    ).run_weekly_sync()
    assert outcome["business_status"] == "no_trading"
    text = notifier.calls[0][1]
    assert "全周休市" in text
    assert "沿用" in text
    assert "2026-02-13" in text


def test_report_without_valuation_service_still_works(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    notifier = FakeNotifier()
    outcome = ReportService(
        store, service, notifier, now_fn=lambda: FRIDAY_CLOSE
    ).run_weekly_sync(manual=True)
    assert outcome["sent"] is True
    text = notifier.calls[0][1]
    assert "估值：暂不可用" in text
