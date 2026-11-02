"""周报边界：未完成周、短周、休市、缺失、比较拆分、旧月线去重与审计。"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from src.core.models import KIND_TRAILING_WEEKLY, TIMEFRAME_WEEK, WeeklyModelRecord
from src.core.regression import Coefficients
from src.data.provider import KlineBar
from src.data.trading_calendar import StaticTradingCalendar
from src.services.report_service import (
    ReportService,
    current_iso_week,
    idempotency_key,
    position_change_components,
)
from src.services.trend_service import SHANGHAI_TZ, WeeklyRefreshResult, WeeklyTrendService

from tests.conftest import BEFORE_CLOSE, FRIDAY_CLOSE


class FakeNotifier:
    def __init__(self, configured: bool = True, ok: bool = True):
        self.configured = configured
        self.ok = ok
        self.calls: list[tuple[str, str]] = []

    def send_markdown(self, title: str, text: str) -> tuple[bool, str | None]:
        self.calls.append((title, text))
        if not self.configured:
            return False, "channel_not_configured"
        return (True, None) if self.ok else (False, "status=500 errcode=-1 errmsg=boom")


def _stub(monkeypatch, service, result=None):
    payload = result or WeeklyRefreshResult(success=True, message="stub", data_cutoff_week="2026-10-26")
    monkeypatch.setattr(service, "refresh_sync", lambda client=None: payload)


def _report(store, service, notifier, now) -> ReportService:
    return ReportService(store, service, notifier, now_fn=lambda: now)


def test_position_change_identity():
    """价格、模型、时间推进三项之和等于新旧位置之差，且可从快照复算。"""
    previous = {
        "timeframe": "week",
        "fit_start": "2026-10-12",
        "multiplier": 2,
        "coefficients": {"slope": 10, "intercept": 100, "deviation": 10},
        "close": 100,
        "projection_week": "2026-10-12",
    }
    current = {
        "timeframe": "week",
        "fit_start": "2026-10-12",
        "multiplier": 2,
        "coefficients": {"slope": 0, "intercept": 200, "deviation": 10},
        "close": 120,
        "projection_week": "2026-10-19",
    }
    parts = position_change_components(previous, current)
    assert parts["price_impact"] == pytest.approx(50)
    assert parts["model_impact"] == pytest.approx(-225)
    assert parts["time_impact"] == pytest.approx(-25)
    assert parts["price_impact"] + parts["model_impact"] + parts["time_impact"] == pytest.approx(
        parts["total"]
    )
    assert parts["total"] == pytest.approx(parts["current_position"] - parts["previous_position"])


def test_before_close_does_not_consume_delivery_slot(store, weekly_published, monkeypatch):
    service, result = weekly_published
    early = WeeklyTrendService(store, now_fn=lambda: BEFORE_CLOSE)
    _stub(monkeypatch, early, result)
    notifier = FakeNotifier()
    outcome = _report(store, early, notifier, BEFORE_CLOSE).run_weekly_sync(manual=True)
    iso_week = current_iso_week(BEFORE_CLOSE)
    assert outcome == {"skipped": True, "reason": "week_incomplete", "iso_week": iso_week}
    assert notifier.calls == []
    assert store.get_report(idempotency_key("000300", iso_week)) is None

    _stub(monkeypatch, service, result)
    later = FakeNotifier()
    sent = _report(store, service, later, FRIDAY_CLOSE).run_weekly_sync(manual=True)
    assert sent["sent"] is True
    assert sent["business_status"] == "normal"
    assert store.get_report(idempotency_key("000300", iso_week))["status"] == "sent"


def test_short_week_uses_last_session_not_a_holiday_note(store, monkeypatch):
    sessions = [
        date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 16),
        date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22),
    ]
    calendar = StaticTradingCalendar(sessions, date(2026, 10, 1), date(2026, 10, 31))
    now = datetime(2026, 10, 22, 15, 5, tzinfo=SHANGHAI_TZ)
    service = WeeklyTrendService(store, now_fn=lambda: now, calendar=calendar)
    _stub(monkeypatch, service)
    store.upsert_weekly_bars(
        {
            "2026-10-12": KlineBar("2026-10-16", 4000, 4000, 4010, 3990),
            "2026-10-19": KlineBar("2026-10-22", 4080, 4100, 4120, 4070),
        }
    )
    store.upsert_daily_quotes([KlineBar("2026-10-22", 4080, 4100, 4120, 4070)])
    store.upsert_weekly_model(_model())
    notifier = FakeNotifier()
    outcome = _report(store, service, notifier, now).run_weekly_sync()
    assert outcome["business_status"] == "normal"
    text = notifier.calls[0][1]
    assert "2026-10-22" in text
    assert "4100.00" in text
    assert "全周休市" not in text
    assert "比较基期 2026-10-16" in text


def test_full_week_closure_is_not_missing_data(store, monkeypatch):
    sessions = [date(2026, 2, 9), date(2026, 2, 10), date(2026, 2, 11), date(2026, 2, 12), date(2026, 2, 13)]
    calendar = StaticTradingCalendar(sessions, date(2026, 2, 1), date(2026, 2, 28))
    now = datetime(2026, 2, 20, 19, 0, tzinfo=SHANGHAI_TZ)
    service = WeeklyTrendService(store, now_fn=lambda: now, calendar=calendar)
    _stub(monkeypatch, service)
    notifier = FakeNotifier()
    outcome = _report(store, service, notifier, now).run_weekly_sync()
    assert outcome["business_status"] == "no_trading"
    assert "全周休市" in notifier.calls[0][1]
    assert "缺失" not in notifier.calls[0][1]


def test_missing_bar_is_not_called_a_holiday(store, monkeypatch):
    sessions = [date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30)]
    calendar = StaticTradingCalendar(sessions, date(2026, 10, 1), date(2026, 10, 31))
    service = WeeklyTrendService(store, now_fn=lambda: FRIDAY_CLOSE, calendar=calendar)
    _stub(monkeypatch, service)
    store.upsert_weekly_model(_model())
    notifier = FakeNotifier()
    outcome = _report(store, service, notifier, FRIDAY_CLOSE).run_weekly_sync()
    assert outcome["business_status"] == "data_error"
    text = notifier.calls[0][1]
    assert "缺失" in text
    assert "全周休市" not in text
    assert store.list_reports()[0]["business_status"] == "data_error"


def test_calendar_out_of_range_is_an_error(store, monkeypatch):
    calendar = StaticTradingCalendar([date(2026, 1, 5)], date(2026, 1, 1), date(2026, 1, 31))
    service = WeeklyTrendService(store, now_fn=lambda: FRIDAY_CLOSE, calendar=calendar)
    _stub(monkeypatch, service)
    notifier = FakeNotifier()
    outcome = _report(store, service, notifier, FRIDAY_CLOSE).run_weekly_sync()
    assert outcome["business_status"] == "data_error"
    assert "日历" in notifier.calls[0][1]
    assert "全周休市" not in notifier.calls[0][1]


def test_missing_model_is_not_normal(store, monkeypatch):
    service = WeeklyTrendService(store, now_fn=lambda: FRIDAY_CLOSE)
    _stub(monkeypatch, service)
    store.upsert_weekly_bars({"2026-10-26": KlineBar("2026-10-30", 3980, 3985.5, 3990, 3970)})
    store.upsert_daily_quotes([KlineBar("2026-10-30", 3980, 3985.5, 3990, 3970)])
    notifier = FakeNotifier()
    outcome = _report(store, service, notifier, FRIDAY_CLOSE).run_weekly_sync()
    assert outcome["business_status"] == "data_error"
    assert "模型不可用" in notifier.calls[0][1]
    assert store.list_reports()[0]["business_status"] == "data_error"


def test_failed_send_retries_after_restart(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    failed = FakeNotifier(ok=False)
    first = _report(store, service, failed, FRIDAY_CLOSE).run_weekly_sync()
    assert first["status"] == "failed"
    key = idempotency_key("000300", first["iso_week"])
    assert store.get_report(key)["status"] == "failed"

    restarted = WeeklyTrendService(store, now_fn=lambda: FRIDAY_CLOSE)
    _stub(monkeypatch, restarted, result)
    notifier = FakeNotifier()
    catchup = _report(store, restarted, notifier, FRIDAY_CLOSE).catchup_if_needed()
    assert catchup is not None
    assert catchup["sent"] is True
    assert store.get_report(key)["status"] == "sent"
    attempts = store.list_report_attempts(key)
    statuses = [item["status"] for item in attempts]
    assert "failed" in statuses
    assert statuses[-1] == "sent"
    assert store.get_report(key)["content"] != ""


def test_sent_monthly_report_blocks_resend_and_keeps_text(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    iso_week = current_iso_week(FRIDAY_CLOSE)
    key = idempotency_key("000300", iso_week)
    store.upsert_report(
        {
            "idempotency_key": key,
            "index_code": "000300",
            "iso_week": iso_week,
            "model_id": "old-monthly",
            "model_kind": "trailing_120m",
            "business_status": "normal",
            "close": 3985.5,
            "close_date": "2026-10-30",
            "region": "lower",
            "position_pct": 32.19,
            "content": "旧月线周报原文",
            "status": "sent",
            "error": None,
        }
    )
    notifier = FakeNotifier()
    outcome = _report(store, service, notifier, FRIDAY_CLOSE).run_weekly_sync()
    assert outcome["reason"] == "already_sent"
    assert notifier.calls == []
    assert store.get_report(key)["content"] == "旧月线周报原文"
    assert store.get_report(key)["model_kind"] == "trailing_120m"


def test_first_weekly_report_does_not_compare_with_monthly_position(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    iso_week = current_iso_week(FRIDAY_CLOSE)
    store.upsert_report(
        {
            "idempotency_key": idempotency_key("000300", "2026-W40"),
            "index_code": "000300",
            "iso_week": "2026-W40",
            "model_id": "old-monthly",
            "model_kind": "trailing_120m",
            "business_status": "normal",
            "close": 3900,
            "close_date": "2026-10-02",
            "region": "lower",
            "position_pct": 32.19,
            "content": "旧月线周报原文 32.19",
            "status": "no_channel",
            "error": "channel_not_configured",
        }
    )
    notifier = FakeNotifier()
    outcome = _report(store, service, notifier, FRIDAY_CLOSE).run_weekly_sync()
    assert outcome["business_status"] == "normal"
    text = notifier.calls[0][1]
    assert "不与旧月线位置比较" in text
    assert "上周位置" not in text
    assert "32.19" not in text
    current = store.get_report(idempotency_key("000300", iso_week))
    assert current["model_kind"] == KIND_TRAILING_WEEKLY
    archived = store.list_report_attempts(idempotency_key("000300", "2026-W40"))
    assert archived == []
    replaced = store.list_report_attempts(idempotency_key("000300", iso_week))
    assert replaced[0]["payload"] != "旧月线周报原文 32.19"


def test_old_no_channel_same_week_is_archived_before_replace(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    iso_week = current_iso_week(FRIDAY_CLOSE)
    key = idempotency_key("000300", iso_week)
    store.upsert_report(
        {
            "idempotency_key": key,
            "index_code": "000300",
            "iso_week": iso_week,
            "model_id": "old-monthly",
            "model_kind": "trailing_120m",
            "business_status": "normal",
            "close": 1,
            "close_date": "2026-10-30",
            "region": "lower",
            "position_pct": 32.19,
            "content": "旧月线周报原文",
            "status": "no_channel",
            "error": "channel_not_configured",
        }
    )
    notifier = FakeNotifier()
    _report(store, service, notifier, FRIDAY_CLOSE).run_weekly_sync()
    attempts = store.list_report_attempts(key)
    assert attempts[0]["payload"] == "旧月线周报原文"
    assert attempts[0]["model_kind"] == "trailing_120m"
    assert store.get_report(key)["content"] != "旧月线周报原文"
    assert "不与旧月线位置比较" in store.get_report(key)["content"]


def test_weekly_snapshot_comparison_is_recomputable(store, weekly_published, monkeypatch):
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    model = store.latest_weekly_model("000300", KIND_TRAILING_WEEKLY)
    previous = {
        "timeframe": "week",
        "model_id": model.model_id,
        "model_kind": model.kind,
        "fit_start": model.fit_start,
        "multiplier": model.multiplier,
        "coefficients": {
            "slope": model.coefficients.slope,
            "intercept": model.coefficients.intercept,
            "deviation": model.coefficients.deviation,
        },
        "close": 3900.0,
        "close_date": "2026-10-23",
        "projection_week": "2026-10-19",
        "position_pct": 10.0,
    }
    store.upsert_report(
        {
            "idempotency_key": idempotency_key("000300", "2026-W43"),
            "index_code": "000300",
            "iso_week": "2026-W43",
            "model_id": model.model_id,
            "model_kind": KIND_TRAILING_WEEKLY,
            "business_status": "normal",
            "close": 3900.0,
            "close_date": "2026-10-23",
            "region": "lower",
            "position_pct": 10.0,
            "content": "上周周线",
            "status": "sent",
            "error": None,
            "snapshot_json": json.dumps(previous, ensure_ascii=False),
        }
    )
    notifier = FakeNotifier()
    _report(store, service, notifier, FRIDAY_CLOSE).run_weekly_sync()
    current = json.loads(store.list_reports()[0]["snapshot_json"])
    parts = position_change_components(previous, current)
    text = notifier.calls[0][1]
    assert f"{parts['price_impact']:+.2f}" in text
    assert f"{parts['model_impact']:+.2f}" in text
    assert f"{parts['time_impact']:+.2f}" in text
    assert parts["price_impact"] + parts["model_impact"] + parts["time_impact"] == pytest.approx(parts["total"])
    assert "不与旧月线" not in text


def test_older_weekly_snapshot_is_not_called_last_week(store, weekly_published, monkeypatch):
    """隔周的周线快照不能当成上周，否则时间推进会算进错误的一周。"""
    service, result = weekly_published
    _stub(monkeypatch, service, result)
    model = store.latest_weekly_model("000300", KIND_TRAILING_WEEKLY)
    previous = {
        "timeframe": "week",
        "fit_start": model.fit_start,
        "multiplier": model.multiplier,
        "coefficients": {
            "slope": model.coefficients.slope,
            "intercept": model.coefficients.intercept,
            "deviation": model.coefficients.deviation,
        },
        "close": 3900.0,
        "projection_week": "2026-09-28",
    }
    store.upsert_report(
        {
            "idempotency_key": idempotency_key("000300", "2026-W40"),
            "index_code": "000300",
            "iso_week": "2026-W40",
            "model_id": model.model_id,
            "model_kind": KIND_TRAILING_WEEKLY,
            "business_status": "normal",
            "close": 3900.0,
            "close_date": "2026-10-02",
            "region": "lower",
            "position_pct": 10.0,
            "content": "更早的周线",
            "status": "sent",
            "error": None,
            "snapshot_json": json.dumps(previous, ensure_ascii=False),
        }
    )
    notifier = FakeNotifier()
    _report(store, service, notifier, FRIDAY_CLOSE).run_weekly_sync()
    text = notifier.calls[0][1]
    assert "与上周周线快照相比" not in text
    assert "没有上一周" in text


def _model() -> WeeklyModelRecord:
    return WeeklyModelRecord(
        model_id="000300|week|trailing_10y_weekly|2026-10-12|2026-10-19|lrc-ltb-week-v1|abc",
        index_code="000300",
        kind=KIND_TRAILING_WEEKLY,
        timeframe=TIMEFRAME_WEEK,
        sample_count=2,
        fit_start="2026-10-12",
        fit_end="2026-10-19",
        fit_last_trade_date="2026-10-22",
        calendar_window_start="2016-10-23",
        calendar_window_end="2026-10-23",
        data_cutoff_week="2026-10-19",
        algorithm_version="lrc-ltb-week-v1",
        data_hash="abc",
        multiplier=2,
        coefficients=Coefficients(0, 4000, 100),
        calculated_at="2026-10-22T16:00:00+08:00",
    )
