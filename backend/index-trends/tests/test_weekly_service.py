"""周线刷新管线：取数校验 → 纯计算 → 事务发布。

脱网：用 httpx MockTransport 返回 fixture 数据，不触网。
"""
from __future__ import annotations

import httpx
import pytest

from src.core.models import (
    KIND_SINCE_INCEPTION_WEEKLY,
    KIND_TRAILING_WEEKLY,
    data_hash,
    weekly_data_hash,
)
from src.data.provider import KlineBar
from src.services.store import Store
from src.services.trend_service import WeeklyTrendService, compute_snapshot_id

from tests.conftest import WEEKLY_FIXED_NOW


def _mock_client(weekly_rows, daily_rows) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        param = str(request.url)
        if "week" in param:
            return httpx.Response(200, json={"code": 0, "msg": "", "data": {"sh000300": {"week": weekly_rows}}})
        return httpx.Response(200, json={"code": 0, "msg": "", "data": {"sh000300": {"day": daily_rows}}})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _rows(bars: list[KlineBar]) -> list[list[str]]:
    return [[b.date, str(b.open), str(b.close), str(b.high), str(b.low)] for b in bars]


@pytest.fixture()
def weekly_service(store: Store) -> WeeklyTrendService:
    return WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)


def test_refresh_publishes_snapshot(weekly_service, store, weekly_bars, weekly_daily_bars):
    client = _mock_client(_rows(weekly_bars), _rows(weekly_daily_bars))
    result = weekly_service.refresh_sync(client)
    assert result.success is True
    assert result.data_cutoff_week == "2026-10-26"
    assert result.data_cutoff_trade_date == "2026-10-30"
    assert result.weekly_count == 1100
    assert result.snapshot_id

    meta = store.get_weekly_data_meta()
    assert meta["snapshot_id"] == result.snapshot_id
    assert meta["data_cutoff_week"] == "2026-10-26"
    stored = store.load_weekly_bars(include_partial=False)
    weeks = sorted(stored)
    closes = [stored[week].close for week in weeks]
    assert meta["weekly_hash"] == weekly_data_hash(weeks, closes)
    assert meta["weekly_hash"] != data_hash(closes)

    # 模型已落库
    kinds = {m.kind for m in store.list_weekly_models("000300")}
    assert KIND_TRAILING_WEEKLY in kinds
    assert KIND_SINCE_INCEPTION_WEEKLY in kinds


def test_refresh_is_idempotent(weekly_service, store, weekly_bars, weekly_daily_bars):
    """重复刷新不产生新模型版本（旧模型不被覆盖）。"""
    client = _mock_client(_rows(weekly_bars), _rows(weekly_daily_bars))
    first = weekly_service.refresh_sync(client)
    count_after_first = len(store.list_weekly_models("000300"))
    second = weekly_service.refresh_sync(client)
    assert second.new_models == []
    assert len(store.list_weekly_models("000300")) == count_after_first
    assert first.snapshot_id == second.snapshot_id


def test_publish_failure_keeps_old_snapshot(store, weekly_bars, weekly_daily_bars):
    """发布失败 → 旧快照仍可读，元数据不变。"""
    service = WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)
    client = _mock_client(_rows(weekly_bars), _rows(weekly_daily_bars))
    first = service.refresh_sync(client)
    assert first.success

    # 制造一次校验失败（篡改日线使收盘对不上）
    bad_daily = [
        KlineBar(b.date, b.open, b.close + 999.0, b.high, b.low) for b in weekly_daily_bars
    ]
    bad_client = _mock_client(_rows(weekly_bars), _rows(bad_daily))
    with pytest.raises(ValueError):
        service.refresh_sync(bad_client)

    meta = store.get_weekly_data_meta()
    assert meta["snapshot_id"] == first.snapshot_id
    assert meta["data_cutoff_week"] == "2026-10-26"


def test_incomplete_week_not_published(store, weekly_bars, weekly_daily_bars):
    """进行中的周落库但标记为 partial，不参与拟合（可展示）。"""
    service = WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)
    client = _mock_client(_rows(weekly_bars), _rows(weekly_daily_bars))
    service.refresh_sync(client)
    complete = store.load_weekly_bars(include_partial=False)
    partial = store.load_partial_weekly_bars()
    assert "2026-11-02" not in complete
    assert "2026-11-02" in partial
    assert "2026-10-26" in complete
    # 拟合只用了完整周
    model = store.latest_weekly_model("000300", "trailing_10y_weekly")
    assert model.data_cutoff_week == "2026-10-26"


def test_daily_quotes_published_with_snapshot(store, weekly_bars, weekly_daily_bars):
    """日线与周K/模型在同一事务发布（供最近收盘定位与交叉校验使用）。"""
    service = WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)
    client = _mock_client(_rows(weekly_bars), _rows(weekly_daily_bars))
    service.refresh_sync(client)
    dailies = store.load_daily_quotes(limit=500)
    assert dailies
    assert max(d.date for d in dailies) == "2026-11-02"


def test_snapshot_id_is_content_derived():
    a = compute_snapshot_id("2026-10-26", "h1", ["m1", "m2"])
    b = compute_snapshot_id("2026-10-26", "h1", ["m2", "m1"])
    assert a == b
    assert a != compute_snapshot_id("2026-10-26", "h2", ["m1", "m2"])
    assert a != compute_snapshot_id("2026-11-02", "h1", ["m1", "m2"])


def test_fetch_rejects_insufficient_history(store, weekly_bars, weekly_daily_bars):
    """周K未覆盖 2005-04 起点 → 拒绝发布。"""
    service = WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)
    short_weekly = [b for b in weekly_bars if b.date >= "2020-01-01"]
    client = _mock_client(_rows(short_weekly), _rows(weekly_daily_bars))
    with pytest.raises(ValueError) as exc:
        service.fetch_and_validate(client)
    assert "2005-04" in str(exc.value)
