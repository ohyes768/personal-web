"""估值服务测试（脱网）。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.data import lixinger as lx
from src.data.trading_calendar import StaticTradingCalendar
from src.services.store import Store
from src.services.valuation_service import (
    STATE_DISABLED,
    STATE_EMPTY,
    STATE_ERROR,
    STATE_OK,
    STATE_STALE,
    ValuationService,
)

TZ = "Asia/Shanghai"


def _calendar(*days: str) -> StaticTradingCalendar:
    sessions = [date.fromisoformat(d) for d in days]
    # 覆盖范围要包住 expected_last_complete_week 的 90 天回看窗口
    return StaticTradingCalendar(
        sessions,
        coverage_start=sessions[0] - timedelta(days=120),
        coverage_end=sessions[-1] + timedelta(days=30),
    )


def _week_sessions(week_start: str) -> list[str]:
    start = date.fromisoformat(week_start)
    return [(start + timedelta(days=i)).isoformat() for i in range(5)]


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


def _ok_payload(date_str: str = "2026-10-30T15:00:00+08:00", pe=12.3456, ratio=0.565952) -> dict:
    return {
        "code": 1,
        "data": [
            {
                "stockCode": "000300",
                "date": date_str,
                lx.METRIC_PE_TTM: pe,
                lx.METRIC_CVPOS: ratio,
            }
        ],
    }


def _service(store, client, now, calendar, token="token") -> ValuationService:
    return ValuationService(
        store,
        token=token,
        calendar=calendar,
        now_fn=lambda: now,
        client_factory=lambda: client,
    )


@pytest.fixture()
def store(tmp_path) -> Store:
    return Store(tmp_path / "valuation.db")


# ---- 无 Token ----
def test_without_token_service_is_disabled_and_does_not_request(store):
    client = _FakeClient(_ok_payload())
    service = _service(
        store,
        client,
        datetime(2026, 10, 30, 19, 0),
        _calendar(*_week_sessions("2026-10-26")),
        token="",
    )
    snapshot = service.refresh()
    assert snapshot["state"] == STATE_DISABLED
    assert snapshot["reason"] == "token_not_configured"
    assert client.calls == 0


# ---- 正常采集 ----
def test_refresh_publishes_values(store):
    client = _FakeClient(_ok_payload())
    service = _service(store, client, datetime(2026, 10, 30, 19, 0), _calendar(*_week_sessions("2026-10-26")))
    snapshot = service.refresh()
    assert snapshot["state"] == STATE_OK
    assert snapshot["target_date"] == "2026-10-30"
    assert snapshot["as_of"] == "2026-10-30"
    assert snapshot["pe_ttm"] == 12.35
    assert snapshot["percentile_pct"] == 56.6
    assert client.calls == 1


def test_cached_target_date_skips_request(store):
    client = _FakeClient(_ok_payload())
    service = _service(store, client, datetime(2026, 10, 30, 19, 0), _calendar(*_week_sessions("2026-10-26")))
    service.refresh()
    snapshot = service.refresh()
    assert client.calls == 1
    assert snapshot["state"] == STATE_OK


def test_new_target_date_requests_again(store):
    client = _FakeClient(_ok_payload())
    calendar = _calendar(*_week_sessions("2026-10-26"), *[
        (date.fromisoformat("2026-11-02") + timedelta(days=i)).isoformat() for i in range(5)
    ])
    service = _service(store, client, datetime(2026, 11, 6, 19, 0), calendar)
    service.refresh("2026-10-30")
    service.refresh("2026-11-06")
    assert client.calls == 2


# ---- 失败与冷却 ----
def test_failure_reports_error_and_keeps_previous_data(store):
    calendar = _calendar(*_week_sessions("2026-10-26"))
    # 先落一条更早日期的成功数据
    older = _FakeClient(_ok_payload(date_str="2026-10-23T15:00:00+08:00"))
    service = _service(store, older, datetime(2026, 10, 30, 19, 0), calendar)
    service.refresh("2026-10-23")

    failing = _FakeClient(error=lx.LixingerError("network_error", "理杏仁请求失败: ConnectError"))
    service = _service(store, failing, datetime(2026, 10, 30, 20, 0), calendar)
    snapshot = service.refresh("2026-10-30")
    assert snapshot["state"] == STATE_ERROR
    assert snapshot["reason"] == "network_error"
    # 旧数据仍在，但状态不冒充 ok
    assert snapshot["as_of"] == "2026-10-23"
    assert snapshot["pe_ttm"] == 12.35


def test_failure_triggers_cooldown(store):
    calendar = _calendar(*_week_sessions("2026-10-26"))
    failing = _FakeClient(error=lx.LixingerError("network_error", "理杏仁请求失败"))
    service = _service(store, failing, datetime(2026, 10, 30, 19, 0), calendar)
    service.refresh()
    assert failing.calls == 1
    service.refresh()
    assert failing.calls == 1   # 冷却期内不重复请求


def test_cooldown_does_not_block_new_target_date(store):
    calendar = _calendar(
        *_week_sessions("2026-10-26"),
        *[(date.fromisoformat("2026-11-02") + timedelta(days=i)).isoformat() for i in range(5)],
    )
    failing = _FakeClient(error=lx.LixingerError("network_error", "理杏仁请求失败"))
    service = _service(store, failing, datetime(2026, 10, 30, 19, 0), calendar)
    service.refresh("2026-10-30")
    service.refresh("2026-11-06")
    assert failing.calls == 2


def test_upstream_business_error_is_sanitized(store):
    client = _FakeClient({"code": 4001, "msg": "no permission for this account"})
    service = _service(store, client, datetime(2026, 10, 30, 19, 0), _calendar(*_week_sessions("2026-10-26")))
    snapshot = service.refresh()
    assert snapshot["state"] == STATE_ERROR
    assert snapshot["reason"] == "upstream_error"
    assert "no permission" not in str(snapshot)


# ---- 状态判定 ----
def test_state_is_stale_when_data_behind_target(store):
    client = _FakeClient(_ok_payload(date_str="2026-10-23T15:00:00+08:00"))
    service = _service(store, client, datetime(2026, 10, 30, 19, 0), _calendar(*_week_sessions("2026-10-26")))
    snapshot = service.refresh()
    assert snapshot["state"] == STATE_STALE
    assert snapshot["reason"] == "not_updated_to_target"
    assert snapshot["as_of"] == "2026-10-23"
    assert snapshot["target_date"] == "2026-10-30"


def test_state_is_empty_without_data(store):
    client = _FakeClient({"code": 1, "data": []})
    service = _service(store, client, datetime(2026, 10, 30, 19, 0), _calendar(*_week_sessions("2026-10-26")))
    snapshot = service.refresh()
    assert snapshot["state"] == STATE_EMPTY
    assert snapshot["percentile_pct"] is None
    assert snapshot["pe_ttm"] is None


def test_missing_values_are_null_not_zero(store):
    client = _FakeClient(_ok_payload())
    service = _service(store, client, datetime(2026, 10, 30, 19, 0), _calendar(*_week_sessions("2026-10-26")))
    service.refresh()
    row = store.latest_valuation("000300", lx.VALUATION_SOURCE, lx.VALUATION_METRIC, lx.VALUATION_WINDOW)
    assert row is not None
    snapshot = ValuationService(store, token="token").status("2026-10-30")
    assert snapshot["pe_ttm"] is not None and snapshot["pe_ttm"] != 0


# ---- 目标日 ----
def test_page_target_is_last_session_of_last_complete_week(store):
    client = _FakeClient(_ok_payload())
    service = _service(store, client, datetime(2026, 10, 30, 19, 0), _calendar(*_week_sessions("2026-10-26")))
    assert service.resolve_page_target_date() == "2026-10-30"


def test_page_target_switches_to_current_week_after_close(store):
    calendar = _calendar(
        *_week_sessions("2026-10-26"),
        *[(date.fromisoformat("2026-11-02") + timedelta(days=i)).isoformat() for i in range(5)],
    )
    client = _FakeClient(_ok_payload())
    service = _service(store, client, datetime(2026, 11, 6, 19, 0), calendar)
    assert service.resolve_page_target_date() == "2026-11-06"


def test_page_target_ignores_in_progress_week(store):
    calendar = _calendar(
        *_week_sessions("2026-10-26"),
        *[(date.fromisoformat("2026-11-02") + timedelta(days=i)).isoformat() for i in range(5)],
    )
    client = _FakeClient(_ok_payload())
    # 周一收盘后：本周尚未结束，目标日仍是上周
    service = _service(store, client, datetime(2026, 11, 2, 16, 0), calendar)
    assert service.resolve_page_target_date() == "2026-10-30"


def test_week_target_date_uses_report_week(store):
    client = _FakeClient(_ok_payload())
    service = _service(store, client, datetime(2026, 10, 30, 19, 0), _calendar(*_week_sessions("2026-10-26")))
    assert service.resolve_week_target_date("2026-10-26") == "2026-10-30"


def test_calendar_unavailable_is_reported_as_error(store):
    client = _FakeClient(_ok_payload())
    # 覆盖范围不含最近完整周：日历越界 → 无法确定目标日
    calendar = _calendar(*_week_sessions("2026-10-26"))
    narrow = StaticTradingCalendar(
        [date.fromisoformat(d) for d in _week_sessions("2026-10-26")],
        coverage_start=date(2026, 10, 26),
        coverage_end=date(2026, 10, 30),
    )
    service = _service(store, client, datetime(2026, 11, 6, 19, 0), narrow)
    snapshot = service.status()
    assert snapshot["state"] == STATE_ERROR
    assert snapshot["reason"] == "calendar_unavailable"
    assert client.calls == 0
