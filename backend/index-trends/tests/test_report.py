"""AC7：周报幂等、渠道未配置、休市周、模型与页面分离。

模块级 autouse：挡住 refresh_sync 的真实网络调用——周报数值验证必须脱网
（design §7：以固定 fixture 验证，不依赖实时网络跑单测）。
"""
from __future__ import annotations

import pytest

from src.core.models import KIND_TRAILING
from src.services.report_service import ReportService, current_iso_week, idempotency_key
from src.services.store import Store
from src.services.trend_service import RefreshResult


@pytest.fixture(autouse=True)
def stub_refresh(monkeypatch, service):
    monkeypatch.setattr(
        service,
        "refresh_sync",
        lambda client=None: RefreshResult(success=True, message="stub", data_cutoff_month="2026-09"),
    )


class FakeNotifier:
    """假通知器：不发真实消息，记录调用。"""

    def __init__(self, configured: bool = True, ok: bool = True):
        self.configured = configured
        self.ok = ok
        self.calls: list[tuple[str, str]] = []

    def is_configured(self) -> bool:
        return self.configured

    def send_markdown(self, title: str, text: str) -> tuple[bool, str | None]:
        self.calls.append((title, text))
        if not self.configured:
            return False, "channel_not_configured"
        return (True, None) if self.ok else (False, "status=500 errcode=-1 errmsg=boom")


def make_report_service(store: Store, service, notifier: FakeNotifier) -> ReportService:
    return ReportService(store, service, notifier, public_url="")


def seed_and_refresh(store, service, fixture_series, monthly_fixture):
    """注入 fixture 行情（含一条 2026-10-28 日线作为周收盘）。"""
    from src.data.provider import KlineBar
    from src.data.validate import to_month_key

    store.upsert_monthly_bars({m: fixture_series.bars[m] for m in fixture_series.months})
    for r in service._compute_models(fixture_series, "2026-09"):
        store.upsert_model(r)
    daily = KlineBar(date="2026-10-28", open=4000.0, close=4050.0, high=4060.0, low=3990.0)
    store.upsert_daily_quotes([daily])
    return daily


def test_report_generated_and_sent(store, service, fixture_series, monthly_fixture):
    seed_and_refresh(store, service, fixture_series, monthly_fixture)
    notifier = FakeNotifier(configured=True)
    report_service = make_report_service(store, service, notifier)
    outcome = report_service.run_weekly_sync()
    assert outcome["sent"] is True
    assert len(notifier.calls) == 1
    title, text = notifier.calls[0]
    assert "宽基趋势观察" in title
    assert "2026-10-28" in text       # 真实收盘日期
    assert "4050.00" in text          # 点位
    reports = store.list_reports()
    assert reports[0]["status"] == "sent"
    assert reports[0]["model_id"] != "unavailable"


def test_no_duplicate_send_within_week(store, service, fixture_series, monthly_fixture):
    seed_and_refresh(store, service, fixture_series, monthly_fixture)
    notifier = FakeNotifier(configured=True)
    report_service = make_report_service(store, service, notifier)
    assert report_service.run_weekly_sync()["sent"] is True
    second = report_service.run_weekly_sync()
    assert second == {"skipped": True, "reason": "already_sent", "iso_week": second["iso_week"]}
    assert len(notifier.calls) == 1   # 未重复发送


def test_no_channel_stored_not_faked(store, service, fixture_series, monthly_fixture):
    """渠道未配置：报告保存 no_channel，不发送不伪报成功；后续可重试发送。"""
    seed_and_refresh(store, service, fixture_series, monthly_fixture)
    notifier = FakeNotifier(configured=False)
    report_service = make_report_service(store, service, notifier)
    outcome = report_service.run_weekly_sync()
    assert outcome["status"] == "no_channel"
    key = idempotency_key("000300", outcome["iso_week"])
    assert store.get_report(key)["status"] == "no_channel"

    # 渠道配置好之后手动触发 → 重试发送同一周报告
    retry_notifier = FakeNotifier(configured=True)
    report_service2 = ReportService(store, service, retry_notifier, public_url="")
    retry = report_service2.run_weekly_sync(manual=True)
    assert retry["sent"] is True
    assert retry_notifier.calls[0][1].startswith("## 宽基趋势观察")


def test_holiday_week_no_trading(store, service, fixture_series, monthly_fixture):
    """整周休市：无当周日线 → no_trading 说明记录，仍走发送流程。"""
    seed_and_refresh(store, service, fixture_series, monthly_fixture)
    # 清掉日线模拟整周休市
    store._conn.execute("DELETE FROM daily_quotes")
    store._conn.commit()
    notifier = FakeNotifier(configured=True)
    report_service = make_report_service(store, service, notifier)
    outcome = report_service.run_weekly_sync()
    assert outcome["business_status"] == "no_trading"
    assert "全周休市" in notifier.calls[0][1]


def test_provider_failure_reported(store, service, fixture_series, monthly_fixture, monkeypatch):
    """行情刷新失败：生成异常摘要而非伪新数据。"""
    seed_and_refresh(store, service, fixture_series, monthly_fixture)

    def boom(client=None):
        raise RuntimeError("腾讯行情请求失败: timeout")

    monkeypatch.setattr(service, "refresh_sync", boom)
    notifier = FakeNotifier(configured=True)
    report_service = make_report_service(store, service, notifier)
    outcome = report_service.run_weekly_sync()
    assert outcome["business_status"] == "data_error"
    assert "timeout" in notifier.calls[0][1]


def test_report_model_separated_from_page(store, service, fixture_series, monthly_fixture):
    """周报模型（持久配置）与页面临时切换完全分离。"""
    seed_and_refresh(store, service, fixture_series, monthly_fixture)
    store.update_report_settings({"model_kind": "since_inception"})
    notifier = FakeNotifier(configured=True)
    report_service = make_report_service(store, service, notifier)
    outcome = report_service.run_weekly_sync()
    assert outcome["sent"] is True
    report = store.list_reports()[0]
    assert report["model_kind"] == "since_inception"    # 用的是配置的模型
    # 页面查询 trailing_120m 不受周报配置影响（页面默认仍是自己的选择）
    page_status = service.current_status(KIND_TRAILING)
    assert page_status["available"] is True


def test_catchup_skips_when_report_sent(store, service, fixture_series, monthly_fixture):
    seed_and_refresh(store, service, fixture_series, monthly_fixture)
    notifier = FakeNotifier(configured=True)
    report_service = make_report_service(store, service, notifier)
    report_service.run_weekly_sync()
    # 已 sent：补发检查返回 None（不重复发送）
    assert report_service.catchup_if_needed() is None
    assert len(notifier.calls) == 1
