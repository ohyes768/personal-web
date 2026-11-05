"""周线 API：字段、旧 kind 别名、旧月线 ID 拒绝、空库与异常状态。GET 不发消息。"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import router
from src.core.models import (
    KIND_SINCE_INCEPTION_WEEKLY,
    KIND_TRAILING,
    KIND_TRAILING_WEEKLY,
    ModelRecord,
    build_model_id,
)
from src.core.regression import ALGORITHM_VERSION, Coefficients
from src.services.trend_service import WeeklyTrendService

from tests.conftest import WEEKLY_FIXED_NOW


@pytest.fixture()
def api_app(store, weekly_series, weekly_daily_bars):
    service = WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)
    service.publish(weekly_series, weekly_daily_bars, service.compute_models(weekly_series))
    app = FastAPI()
    app.include_router(router)
    app.state.trend_service = service
    app.state.store = store
    return app


@pytest.fixture()
def client(api_app):
    with TestClient(api_app) as test_client:
        yield test_client


@pytest.fixture()
def empty_client(store):
    service = WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)
    app = FastAPI()
    app.include_router(router)
    app.state.trend_service = service
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "index-trends"


def test_indices_overview_is_weekly(client):
    body = client.get("/api/indices").json()
    index = body["indices"][0]
    assert index["index_code"] == "000300"
    assert index["inception_week"] == "2005-04-04"
    kinds = index["current_models"]
    assert KIND_TRAILING_WEEKLY in kinds
    assert KIND_SINCE_INCEPTION_WEEKLY in kinds
    assert kinds[KIND_TRAILING_WEEKLY]["timeframe"] == "week"
    assert kinds[KIND_TRAILING_WEEKLY]["sample_count"] > 0
    assert "months" not in kinds[KIND_TRAILING_WEEKLY]
    assert body["data_status"]["state"] == "ok"
    assert body["data_status"]["data_cutoff_week"] == "2026-10-26"
    assert "data_cutoff_month" not in body["data_status"]


def test_history_windows_use_week_fields(client):
    body = client.get("/api/indices/000300/history").json()
    assert len(body["windows"]) == 4
    first = body["windows"][0]
    assert first["stable_id"] == "fixed-2005-04"
    assert first["sample_count"] > 0
    assert first["observation_end_week"]
    assert "observation_end_month" not in first
    assert body["all_history"]["model_id"]
    assert body["all_history"]["sample_count"] > 0
    assert "非2005年时点已知通道" in body["all_history"]["note"]


def test_history_chart_keeps_holiday_slots_and_observation_note(client):
    history = client.get("/api/indices/000300/history").json()
    model_id = history["windows"][0]["model_id"]
    chart = client.get(f"/api/indices/000300/chart?model={model_id}&scope=history").json()
    fit = chart["fit_series"]
    assert fit["weeks"][0] == chart["model"]["fit_start"]
    assert fit["weeks"][-1] == chart["fit_boundary_week"]
    assert "months" not in fit
    assert chart["model"]["timeframe"] == "week"
    bar_weeks = {bar["week_start"] for bar in chart["bars"]}
    gaps = [week for week in fit["weeks"] if week not in bar_weeks]
    assert gaps, "整周休市应留在时间轴上，而不是被挤掉"
    assert chart["extension_series"]["weeks"][0] == chart["fit_boundary_week"]
    assert "非目标价" not in (chart["extend_note"] or "")
    assert "观察" in chart["extend_note"]
    assert chart["snapshot_id"]


def test_all_history_matches_since_inception_without_extension(client):
    history = client.get("/api/indices/000300/history").json()
    chart = client.get(
        f"/api/indices/000300/chart?model={history['all_history']['model_id']}&scope=history"
    ).json()
    assert chart["model"]["kind"] == KIND_SINCE_INCEPTION_WEEKLY
    assert chart["extension_series"] is None
    assert chart["fit_series"]["weeks"][0] == chart["model"]["fit_start"]
    assert len(chart["fit_series"]["weeks"]) >= chart["model"]["sample_count"]


def test_current_chart_extends_52_weeks_and_marks_partial(client):
    chart = client.get(
        "/api/indices/000300/chart?model=kind:trailing_10y_weekly&scope=current"
    ).json()
    assert chart["model"]["kind"] == KIND_TRAILING_WEEKLY
    assert chart["model"]["data_cutoff_week"] == "2026-10-26"
    ext = chart["extension_series"]
    assert ext["weeks"][0] == chart["model"]["fit_end"]
    assert len(ext["weeks"]) == 53
    end = chart["model"]["fit_end"]
    from datetime import date

    assert ext["weeks"][-1] == (date.fromisoformat(end) + timedelta(weeks=52)).isoformat()
    assert "非目标价" in chart["extend_note"]
    partial = [bar for bar in chart["bars"] if bar["partial"]]
    assert partial
    assert partial[-1]["week_start"] == "2026-11-02"
    assert all(not bar["partial"] or bar["week_start"] == "2026-11-02" for bar in chart["bars"])


def test_legacy_kind_alias_resolves_to_weekly(client):
    weekly = client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    legacy = client.get("/api/indices/000300/status?model=trailing_120m").json()
    assert legacy["model"]["model_id"] == weekly["model"]["model_id"]
    assert legacy["model"]["timeframe"] == "week"
    assert legacy["projection_week"] == "2026-11-02"
    assert legacy["price_as_of"] == "2026-11-02"
    chart = client.get("/api/indices/000300/chart?model=kind:since_inception&scope=current").json()
    assert chart["model"]["kind"] == KIND_SINCE_INCEPTION_WEEKLY
    assert chart["model"]["timeframe"] == "week"


def test_status_switches_model_without_touching_archived_report_settings(client, api_app):
    before = api_app.state.store.get_report_settings()
    trailing = client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    since = client.get("/api/indices/000300/status?model=since_inception_weekly").json()
    after = api_app.state.store.get_report_settings()
    assert before["model_kind"] == after["model_kind"] == KIND_TRAILING_WEEKLY
    assert trailing["model"]["model_id"] != since["model"]["model_id"]
    assert trailing["snapshot_id"] == since["snapshot_id"]
    assert trailing["upper"] != since["upper"] or trailing["lower"] != since["lower"]
    assert trailing["model"]["sample_count"] != since["model"]["sample_count"]
    assert client.get("/api/reports").json()["reports"] == []


def test_chart_and_status_share_snapshot(client):
    status = client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    chart = client.get(
        "/api/indices/000300/chart?model=kind:trailing_10y_weekly&scope=current"
    ).json()
    assert status["snapshot_id"] == chart["snapshot_id"]
    assert status["model"]["model_id"] == chart["model"]["model_id"]


def test_old_monthly_model_id_is_rejected(client, api_app):
    record = ModelRecord(
        model_id=build_model_id("000300", KIND_TRAILING, "2016-10", "2026-09", "abc", ALGORITHM_VERSION),
        index_code="000300",
        kind=KIND_TRAILING,
        fit_start="2016-10",
        fit_end="2026-09",
        months=120,
        algorithm_version=ALGORITHM_VERSION,
        data_cutoff_month="2026-09",
        data_hash="abc",
        multiplier=2,
        coefficients=Coefficients(1, 2, 3),
        calculated_at="2026-10-01T00:00:00+08:00",
    )
    api_app.state.store.upsert_model(record)
    resp = client.get(f"/api/indices/000300/chart?model={record.model_id}&scope=current")
    assert resp.status_code == 409
    assert "月线" in resp.json()["detail"]


def test_invalid_kind_unknown_index_and_model(client):
    assert client.get("/api/indices/000300/chart?model=kind:bogus").status_code == 400
    assert client.get("/api/indices/000905/history").status_code == 404
    assert client.get("/api/indices/000300/chart?model=no-such-model").status_code == 404
    assert client.get("/api/indices/000300/status?model=weird").status_code == 400


def test_empty_library_is_visible(empty_client):
    body = empty_client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    assert body["available"] is False
    assert body["reason"] == "model_not_ready"
    assert body["data_status"]["state"] == "empty"
    history = empty_client.get("/api/indices/000300/history").json()
    assert history["windows"] == []
    assert history["all_history"] is None


def test_stale_and_error_keep_last_snapshot_readable(client, api_app):
    store = api_app.state.store
    store._conn.execute(
        "UPDATE weekly_data_meta SET data_cutoff_week = ? WHERE id = 1",
        ("2020-01-06",),
    )
    store._conn.commit()
    stale = client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    assert stale["available"] is True
    assert stale["data_status"]["state"] == "stale"
    assert stale["close"] is not None

    store.record_weekly_failure("周K收盘与日线不一致")
    failed = client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    assert failed["data_status"]["state"] == "error"
    assert "不一致" in failed["data_status"]["reason"]
    assert failed["available"] is True
    assert failed["snapshot_id"]


def test_refresh_with_mocked_provider(client, monkeypatch, weekly_bars, weekly_daily_bars):
    from src.data import provider as pv

    def fake(symbol, period, count, client_):
        return weekly_bars if period == "week" else weekly_daily_bars

    monkeypatch.setattr(pv, "fetch_kline", fake)
    resp = client.post("/api/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data_cutoff_week"] == "2026-10-26"
    assert body["weekly_count"] == 1100
    assert body["snapshot_id"]
    assert "data_cutoff_month" not in body
    assert "monthly_count" not in body


def test_refresh_provider_failure_visible(client, monkeypatch):
    from src.data import provider as pv

    def boom(symbol, period, count, client_):
        raise pv.ProviderError("腾讯行情 HTTP 503")

    monkeypatch.setattr(pv, "fetch_kline", boom)
    resp = client.post("/api/refresh")
    assert resp.status_code == 502
    assert "腾讯行情" in resp.json()["detail"]


def test_get_does_not_create_reports(client):
    assert client.get("/api/reports").json()["reports"] == []
    client.get("/api/indices/000300/status?model=trailing_10y_weekly")
    client.get("/api/indices/000300/chart?model=kind:trailing_10y_weekly&scope=current")
    client.get("/api/indices/000300/history")
    assert client.get("/api/reports").json()["reports"] == []
