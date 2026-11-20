"""多指数 × 双指标：注册表、存储隔离、旧库迁移、PB 分位、接口白名单。

这些用例守住三件容易复发的事：
1. 两个指数的行情/模型互不清库（`DELETE FROM weekly_bars` 曾是不带条件的）；
2. 旧库升级后沪深300 的数据一条不丢，且归到它自己的 index_code；
3. PB 与 PE 各自判状态——一条缺失不能把另一条判成失败。
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import router
from src.core.indexes import BY_CODE, DEFAULT_INDEX_CODE, index_codes
from src.data import lixinger as lx
from src.data.trading_calendar import StaticTradingCalendar
from src.services.store import Store
from src.services.trend_service import WeeklyTrendService
from src.services.valuation_service import ValuationService

from tests.conftest import FRIDAY_CLOSE, WEEKLY_FIXED_NOW

SN = "sz399673"


# ---- 注册表 ----
def test_registry_lists_both_indexes_with_own_inception():
    assert index_codes() == ("000300", "399673")
    assert BY_CODE["399673"].symbol == "sz399673"
    assert BY_CODE["399673"].inception_week == "2014-06-16"
    # 起点不共用：创业板50 不能套沪深300 的 2005-04 边界
    assert BY_CODE["399673"].earliest_weekly > BY_CODE["000300"].earliest_weekly


# ---- 存储隔离 ----
def test_publishing_one_index_keeps_the_other(store, weekly_series, weekly_daily_bars):
    service = WeeklyTrendService(store, now_fn=lambda: FRIDAY_CLOSE)
    models_a = service.compute_models(DEFAULT_INDEX_CODE, weekly_series)
    service.publish(DEFAULT_INDEX_CODE, weekly_series, weekly_daily_bars, models_a)
    baseline = len(store.load_weekly_bars(index_code=DEFAULT_INDEX_CODE))

    models_b = service.compute_models("399673", weekly_series)
    service.publish("399673", weekly_series, weekly_daily_bars, models_b)

    assert len(store.load_weekly_bars(index_code=DEFAULT_INDEX_CODE)) == baseline
    assert len(store.load_weekly_bars(index_code="399673")) == baseline
    # 有通道的指数出模型；没有通道的只落价格，不产模型
    assert store.latest_weekly_model(DEFAULT_INDEX_CODE, "since_inception_weekly")
    assert store.latest_weekly_model("399673", "since_inception_weekly") is None
    assert store.get_weekly_data_meta(DEFAULT_INDEX_CODE)["snapshot_id"]
    assert store.get_weekly_data_meta("399673")["snapshot_id"]


def test_failure_flag_is_isolated_per_index(store, weekly_series, weekly_daily_bars):
    service = WeeklyTrendService(store, now_fn=lambda: FRIDAY_CLOSE)
    models = service.compute_models(DEFAULT_INDEX_CODE, weekly_series)
    service.publish(DEFAULT_INDEX_CODE, weekly_series, weekly_daily_bars, models)
    store.record_weekly_failure("399673 抓取失败", "399673")
    assert store.get_weekly_data_meta("399673")["last_error"] == "399673 抓取失败"
    assert store.get_weekly_data_meta(DEFAULT_INDEX_CODE)["last_error"] is None


# ---- 旧库迁移 ----
_OLD_SCHEMA = """
CREATE TABLE monthly_bars (month TEXT PRIMARY KEY, date TEXT NOT NULL, open REAL NOT NULL,
    close REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL);
CREATE TABLE daily_quotes (date TEXT PRIMARY KEY, open REAL NOT NULL, close REAL NOT NULL,
    high REAL NOT NULL, low REAL NOT NULL);
CREATE TABLE data_meta (id INTEGER PRIMARY KEY CHECK (id = 1), provider TEXT NOT NULL,
    captured_at TEXT NOT NULL, monthly_cutoff_month TEXT, monthly_hash TEXT);
CREATE TABLE weekly_bars (week_start TEXT PRIMARY KEY, date TEXT NOT NULL, open REAL NOT NULL,
    close REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
    is_partial INTEGER NOT NULL DEFAULT 0);
CREATE TABLE weekly_data_meta (id INTEGER PRIMARY KEY CHECK (id = 1), provider TEXT NOT NULL,
    captured_at TEXT NOT NULL, data_cutoff_week TEXT, data_cutoff_trade_date TEXT,
    weekly_hash TEXT, snapshot_id TEXT, last_error TEXT, last_error_at TEXT);
CREATE TABLE index_valuations (index_code TEXT NOT NULL, source TEXT NOT NULL,
    metric TEXT NOT NULL, window TEXT NOT NULL, date TEXT NOT NULL, pe_ttm REAL NOT NULL,
    percentile_ratio REAL NOT NULL, captured_at TEXT NOT NULL,
    PRIMARY KEY (index_code, source, metric, window, date));
CREATE TABLE valuation_fetch_meta (id INTEGER PRIMARY KEY CHECK (id = 1),
    index_code TEXT NOT NULL DEFAULT '000300', target_date TEXT, last_attempt_at TEXT,
    last_success_at TEXT, last_error TEXT);
"""


@pytest.fixture()
def legacy_db(tmp_path: Path) -> Path:
    """一份 006 之前的库：单指数结构 + 一条 PE 估值。"""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(_OLD_SCHEMA)
    conn.execute(
        "INSERT INTO weekly_bars VALUES ('2026-10-26','2026-10-30',1,2,3,0.5,0)"
    )
    conn.execute(
        "INSERT INTO weekly_data_meta VALUES (1,'Tencent Finance','2026-10-30T19:00:00+08:00',"
        "'2026-10-26','2026-10-30','h','snap-1',NULL,NULL)"
    )
    conn.execute(
        "INSERT INTO index_valuations VALUES "
        "('000300','lixinger','pe_ttm_mcw','y10','2026-10-29',26.9,0.03,'2026-10-30T18:30:00+08:00')"
    )
    conn.execute(
        "INSERT INTO valuation_fetch_meta VALUES "
        "(1,'000300','2026-10-30','2026-10-30T18:30:00+08:00','2026-10-30T18:30:00+08:00',NULL)"
    )
    conn.commit()
    conn.close()
    return path


def test_legacy_db_is_migrated_without_losing_rows(legacy_db: Path):
    store = Store(legacy_db)

    # 旧行归到 000300，一条不丢
    assert list(store.load_weekly_bars(index_code="000300")) == ["2026-10-26"]
    assert store.get_weekly_data_meta("000300")["snapshot_id"] == "snap-1"
    # 新指数补空行，状态是 empty 而不是崩
    assert store.get_weekly_data_meta("399673") == {
        "provider": "",
        "captured_at": "",
        "data_cutoff_week": None,
        "data_cutoff_trade_date": None,
        "weekly_hash": None,
        "snapshot_id": None,
        "last_error": None,
        "last_error_at": None,
    }
    # 旧 PE 估值回填进历史表，切换读路径不丢历史
    rows = store.list_valuation_history("000300", "lixinger", "pe_ttm_mcw", "y10")
    assert [r["value"] for r in rows] == [26.9]
    # 迁移记账，重复打开不重复执行
    assert (
        store._conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version='006_multi_index'"
        ).fetchone()
        is not None
    )
    store.close()
    twice = Store(legacy_db)
    assert len(twice.load_weekly_bars(index_code="000300")) == 1
    twice.close()


# ---- 双指标解析 ----
def _row(**kwargs) -> dict:
    base = {"stockCode": "399673", "date": "2026-11-18T00:00:00+08:00"}
    base.update(kwargs)
    return base


def test_parse_yields_one_point_per_metric():
    body = {
        "code": 1,
        "data": [
            _row(
                **{
                    "pe_ttm.mcw": 37.9,
                    "pe_ttm.y10.mcw.cvpos": 0.7,
                    "pb.mcw": 6.9,
                    "pb.y10.mcw.cvpos": 0.2,
                }
            )
        ],
    }
    points = lx.parse_fundamental(body, "399673", "2026-11-19")
    assert {p.metric for p in points} == {"pe_ttm_mcw", "pb_mcw"}
    pb = next(p for p in points if p.metric == "pb_mcw")
    assert (pb.value, pb.percentile_ratio) == (6.9, 0.2)


def test_missing_pb_does_not_drop_pe():
    body = {
        "code": 1,
        "data": [_row(**{"pe_ttm.mcw": 37.9, "pe_ttm.y10.mcw.cvpos": 0.7})],
    }
    points = lx.parse_fundamental(body, "399673", "2026-11-19")
    assert [p.metric for p in points] == ["pe_ttm_mcw"]


# ---- 接口 ----
def _calendar() -> StaticTradingCalendar:
    days = [date(2026, 10, 26) + timedelta(days=i) for i in range(5)]
    return StaticTradingCalendar(
        days,
        coverage_start=days[0] - timedelta(days=120),
        coverage_end=days[-1] + timedelta(days=30),
    )


@pytest.fixture()
def api_client(store, weekly_series, weekly_daily_bars):
    trend = WeeklyTrendService(store, now_fn=lambda: FRIDAY_CLOSE)
    models = trend.compute_models(DEFAULT_INDEX_CODE, weekly_series)
    trend.publish(DEFAULT_INDEX_CODE, weekly_series, weekly_daily_bars, models)
    valuation = ValuationService(
        store,
        token="token",
        calendar=_calendar(),
        now_fn=lambda: datetime(2026, 10, 30, 19, 0),
    )
    app = FastAPI()
    app.include_router(router)
    app.state.trend_service = trend
    app.state.valuation_service = valuation
    with TestClient(app) as client:
        yield client, store


def test_unknown_index_is_404_with_supported_list(api_client):
    client, _ = api_client
    resp = client.get(f"/api/indices/{SN}/status?model=trailing_10y_weekly")
    assert resp.status_code == 404
    assert "399673" in resp.json()["detail"]


def test_status_reports_both_metrics(api_client):
    client, store = api_client
    store.publish_valuation(
        "399673", "lixinger", "pb_mcw", "y10", [("2026-10-30", 6.9, 0.195)], "2026-10-30"
    )
    store.publish_valuation(
        "399673", "lixinger", "pe_ttm_mcw", "y10", [("2026-10-30", 37.9, 0.70)], "2026-10-30"
    )
    body = client.get("/api/indices/399673/status?model=trailing_10y_weekly").json()
    valuation = body["valuation"]
    assert set(valuation["metrics"]) == {"pe_ttm_mcw", "pb_mcw"}
    pb = valuation["metrics"]["pb_mcw"]
    assert pb["state"] == "ok"
    assert pb["value"] == 6.9
    assert pb["percentile_pct"] == 19.5
    # 顶层仍按 PE-TTM 平铺（既有页面与简报按这个名字读）
    assert valuation["pe_ttm"] == 37.9
    assert valuation["percentile_pct"] == 70.0


def test_valuation_history_endpoint_returns_series(api_client):
    client, store = api_client
    store.publish_valuation(
        "399673",
        "lixinger",
        "pb_mcw",
        "y10",
        [("2026-10-29", 6.8, 0.20), ("2026-10-30", 6.9, 0.195)],
        "2026-10-30",
    )
    body = client.get("/api/indices/399673/valuation/history?metric=pb_mcw").json()
    assert body["metric"] == "pb_mcw"
    assert body["dates"] == ["2026-10-29", "2026-10-30"]
    assert body["percentiles"] == [20.0, 19.5]


def test_valuation_history_rejects_unknown_metric(api_client):
    client, _ = api_client
    resp = client.get("/api/indices/399673/valuation/history?metric=pe")
    assert resp.status_code == 400
    assert "pb_mcw" in resp.json()["detail"]


# ---- 只做估值的指数（没有通道）----
def test_index_without_channel_still_collects_prices(api_client):
    client, _ = api_client
    entries = {i["index_code"]: i for i in client.get("/api/indices").json()["indices"]}
    assert entries["000300"]["has_channel"] is True
    assert entries["000300"]["available_model_kinds"]
    # 没有通道 ≠ 没有行情：399673 照旧采价格，只是不出模型
    assert entries["399673"]["has_channel"] is False
    assert entries["399673"]["kind"] == "price_index"
    assert entries["399673"]["available_model_kinds"] == []


def test_channel_endpoints_reject_index_without_channel(api_client):
    client, _ = api_client
    chart = client.get("/api/indices/399673/chart?model=kind:trailing_10y_weekly")
    history = client.get("/api/indices/399673/history")
    assert chart.status_code == 409
    assert history.status_code == 409
    assert "通道" in chart.json()["detail"]


def test_prices_endpoint_works_without_channel(api_client, weekly_series, weekly_daily_bars):
    client, store = api_client
    trend = client.app.state.trend_service
    models = trend.compute_models("399673", weekly_series)
    assert models == []  # 无通道指数不产出模型
    trend.publish("399673", weekly_series, weekly_daily_bars, models)
    body = client.get("/api/indices/399673/prices?weeks=30").json()
    assert body["has_channel"] is False
    assert len(body["bars"]) == 30
    assert body["close"] is not None


def test_status_of_channel_less_index_has_no_channel_fields(
    api_client, weekly_series, weekly_daily_bars
):
    client, _ = api_client
    trend = client.app.state.trend_service
    trend.publish("399673", weekly_series, weekly_daily_bars, [])
    body = client.get("/api/indices/399673/status?model=trailing_10y_weekly").json()
    assert body["has_channel"] is False
    assert body["close"] is not None
    # 通道字段一律不出现，避免调用方把价格读成通道位置
    assert "position_pct" not in body
    assert "upper" not in body
    assert set(body["valuation"]["metrics"]) == {"pe_ttm_mcw", "pb_mcw"}


def test_valuation_endpoint_needs_no_model(api_client):
    client, store = api_client
    store.publish_valuation(
        "399673", "lixinger", "pb_mcw", "y10", [("2026-10-30", 6.9, 0.195)], "2026-10-30"
    )
    body = client.get("/api/indices/399673/valuation").json()
    assert body["metrics"]["pb_mcw"]["percentile_pct"] == 19.5
    assert body["metrics"]["pb_mcw"]["state"] == "ok"


def test_daily_market_job_refreshes_every_index(store, monkeypatch):
    """行情对每个指数都要采：没有通道的指数也要价格走势。"""
    import src.main as main_module

    refreshed: list[str] = []

    async def fake_refresh(self, code: str) -> object:
        refreshed.append(code)
        return {"index_code": code, "success": True}

    monkeypatch.setattr(main_module.WeeklyTrendService, "refresh", fake_refresh)
    with TestClient(main_module.create_app()) as client:
        scheduler = client.app.state.scheduler
        client.portal.call(scheduler._run_daily)
    assert sorted(refreshed) == sorted(index_codes())
