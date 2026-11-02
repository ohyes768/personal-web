"""周报主路径：发送、去重、无渠道重试、异常、与页面配置分离。"""
from __future__ import annotations

import pytest

from src.core.models import KIND_SINCE_INCEPTION_WEEKLY, KIND_TRAILING_WEEKLY
from src.services.report_service import ReportService, current_iso_week, idempotency_key

from tests.conftest import FRIDAY_CLOSE


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


@pytest.fixture()
def ready(weekly_published, monkeypatch):
    service, result = weekly_published
    monkeypatch.setattr(service, "refresh_sync", lambda client=None: result)
    return service, result


def _service(store, trend, notifier) -> ReportService:
    return ReportService(store, trend, notifier, public_url="", now_fn=lambda: FRIDAY_CLOSE)


def test_report_generated_and_sent(store, ready):
    service, _result = ready
    notifier = FakeNotifier()
    outcome = _service(store, service, notifier).run_weekly_sync()
    assert outcome["sent"] is True
    assert outcome["business_status"] == "normal"
    title, text = notifier.calls[0]
    assert "宽基趋势观察" in title
    assert "2026-10-30" in text
    assert "个交易周" in text
    assert "120个月" not in text
    assert "比较基期" in text
    report = store.list_reports()[0]
    assert report["status"] == "sent"
    assert report["model_kind"] == KIND_TRAILING_WEEKLY
    assert report["model_id"] != "unavailable"
    assert report["snapshot_json"]


def test_no_duplicate_send_within_week(store, ready):
    service, _result = ready
    notifier = FakeNotifier()
    report_service = _service(store, service, notifier)
    assert report_service.run_weekly_sync()["sent"] is True
    second = report_service.run_weekly_sync()
    iso_week = current_iso_week(FRIDAY_CLOSE)
    assert second == {"skipped": True, "reason": "already_sent", "iso_week": iso_week}
    assert len(notifier.calls) == 1


def test_no_channel_stored_not_faked(store, ready):
    service, result = ready
    notifier = FakeNotifier(configured=False)
    outcome = _service(store, service, notifier).run_weekly_sync()
    assert outcome["status"] == "no_channel"
    key = idempotency_key("000300", outcome["iso_week"])
    assert store.get_report(key)["status"] == "no_channel"

    retry_notifier = FakeNotifier(configured=True)
    retry = ReportService(
        store, service, retry_notifier, now_fn=lambda: FRIDAY_CLOSE
    ).run_weekly_sync(manual=True)
    assert retry["sent"] is True
    assert result.snapshot_id
    assert "个交易周" in retry_notifier.calls[0][1]


def test_provider_failure_is_data_error_not_a_normal_summary(store, ready, monkeypatch):
    service, _result = ready

    def boom(client=None):
        raise RuntimeError("腾讯行情请求失败: timeout")

    monkeypatch.setattr(service, "refresh_sync", boom)
    notifier = FakeNotifier()
    outcome = _service(store, service, notifier).run_weekly_sync()
    assert outcome["business_status"] == "data_error"
    assert "timeout" in notifier.calls[0][1]
    assert "全周休市" not in notifier.calls[0][1]
    assert store.list_reports()[0]["business_status"] == "data_error"


def test_report_model_separated_from_page(store, ready):
    service, _result = ready
    store.update_report_settings({"model_kind": KIND_SINCE_INCEPTION_WEEKLY})
    notifier = FakeNotifier()
    outcome = _service(store, service, notifier).run_weekly_sync()
    assert outcome["sent"] is True
    report = store.list_reports()[0]
    assert report["model_kind"] == KIND_SINCE_INCEPTION_WEEKLY
    page = service.current_status(KIND_TRAILING_WEEKLY)
    assert page["available"] is True
    assert page["model"]["kind"] == KIND_TRAILING_WEEKLY
    assert store.get_report_settings()["model_kind"] == KIND_SINCE_INCEPTION_WEEKLY


def test_catchup_skips_when_report_sent(store, ready):
    service, _result = ready
    notifier = FakeNotifier()
    report_service = _service(store, service, notifier)
    report_service.run_weekly_sync()
    assert report_service.catchup_if_needed() is None
    assert len(notifier.calls) == 1


def test_disabled_skips_until_manual(store, ready):
    service, _result = ready
    store.update_report_settings({"enabled": 0})
    notifier = FakeNotifier()
    report_service = _service(store, service, notifier)
    skipped = report_service.run_weekly_sync()
    assert skipped["reason"] == "disabled"
    assert notifier.calls == []
    sent = report_service.run_weekly_sync(manual=True)
    assert sent["sent"] is True
