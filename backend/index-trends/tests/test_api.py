"""AC1/AC6/AC8 支撑：API 集成测试（脱网，手动装配 app，不跑真实调度）。"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import router
from src.data.provider import KlineBar
from src.data.validate import to_month_key
from src.services.trend_service import KIND_SINCE_INCEPTION, KIND_TRAILING

from tests.conftest import FIXED_NOW


@pytest.fixture()
def client(store, service, fixture_series, monthly_fixture):
    app = FastAPI()
    app.include_router(router)
    app.state.trend_service = service
    # 注入行情与模型（等价于一次成功 refresh 的产物）
    store.upsert_monthly_bars({m: fixture_series.bars[m] for m in fixture_series.months})
    # 未完成月（2026-10）仅展示、不参加拟合
    store.upsert_monthly_bars(
        {"2026-10": KlineBar(date="2026-10-28", open=4000.0, close=4060.0, high=4070.0, low=3980.0)}
    )
    store.upsert_daily_quotes(
        [KlineBar(date="2026-10-28", open=4000.0, close=4050.0, high=4060.0, low=3990.0)]
    )
    for r in service._compute_models(fixture_series, "2026-09"):
        store.upsert_model(r)
    store.set_data_meta("tencent", "2026-09", "abc123")
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "index-trends"


def test_indices_overview(client):
    body = client.get("/api/indices").json()
    assert body["indices"][0]["index_code"] == "000300"   # 字符串
    kinds = body["indices"][0]["current_models"]
    assert KIND_TRAILING in kinds and KIND_SINCE_INCEPTION in kinds
    assert kinds[KIND_TRAILING]["fit_start"] == "2016-10"


def test_history_windows(client):
    body = client.get("/api/indices/000300/history").json()
    assert len(body["windows"]) == 4
    first = body["windows"][0]
    assert first["stable_id"] == "fixed-2005-04"
    assert first["fit_start"] == "2005-04"
    assert first["observation_end_month"] == "2018-03"
    assert body["all_history"]["sample_fitted"] is True
    assert "非2005年时点已知通道" in body["all_history"]["note"]


def test_history_chart_fixed_window(client):
    history = client.get("/api/indices/000300/history").json()
    model_id = history["windows"][0]["model_id"]
    chart = client.get(f"/api/indices/000300/chart?model={model_id}&scope=history").json()
    assert chart["fit_boundary_month"] == "2015-03"
    # 拟合区 120 个月
    assert len(chart["fit_series"]["months"]) == 120
    # 观察区 36 个月（含首尾）
    assert len(chart["extension_series"]["months"]) == 37  # 首点为拟合末端衔接点
    assert chart["bars"][0]["month"] == "2005-04"
    assert all(not b["partial"] for b in chart["bars"])
    # 上下轨对称于中线
    mid = chart["fit_series"]["mid"][0]
    upper = chart["fit_series"]["upper"][0]
    lower = chart["fit_series"]["lower"][0]
    assert upper - mid == pytest.approx(mid - lower)


def test_all_history_chart_matches_since_inception(client):
    history = client.get("/api/indices/000300/history").json()
    all_model = history["all_history"]["model_id"]
    chart = client.get(f"/api/indices/000300/chart?model={all_model}&scope=history").json()
    assert chart["model"]["kind"] == KIND_SINCE_INCEPTION
    assert len(chart["fit_series"]["months"]) == 258      # 全样本
    assert chart["extension_series"] is None              # 全历史不延伸


def test_current_chart_trailing_with_future_extension(client):
    chart = client.get(
        "/api/indices/000300/chart?model=kind:trailing_120m&scope=current"
    ).json()
    assert chart["model"]["kind"] == KIND_TRAILING
    assert len(chart["fit_series"]["months"]) == 120
    ext = chart["extension_series"]
    assert ext["months"][0] == "2026-09"                  # 与拟合末端衔接
    assert ext["months"][-1] == "2027-09"                 # 未来延伸 12 个月
    assert "非目标价" in chart["extend_note"]
    assert chart["bars"][-1]["partial"] is True           # 2026-10 未完成月仅展示


def test_current_chart_kind_shorthand_rejects_invalid(client):
    assert (
        client.get("/api/indices/000300/chart?model=kind:bogus").status_code == 400
    )


def test_current_status_both_models(client):
    for kind in (KIND_TRAILING, KIND_SINCE_INCEPTION):
        body = client.get(f"/api/indices/000300/status?model={kind}").json()
        assert body["available"] is True
        assert body["price_as_of"] == "2026-10-28"
        assert body["projection_month"] == "2026-10"
        assert body["position_pct"] is not None   # position 不裁剪（R4），只验证有值
        assert body["region"] in {"below_channel", "lower", "middle", "upper", "above_channel"}
        assert body["model"]["kind"] == kind              # 全部数值来自所选模型


def test_status_model_cache_isolation(client):
    """切换模型不得读取另一模型的轨道（AC6/契约）。"""
    a = client.get("/api/indices/000300/status?model=trailing_120m").json()
    b = client.get("/api/indices/000300/status?model=since_inception").json()
    assert a["model"]["model_id"] != b["model"]["model_id"]
    assert a["upper"] != b["upper"] or a["lower"] != b["lower"]


def test_report_settings_roundtrip(client):
    original = client.get("/api/report-settings").json()
    assert original["model_kind"] == KIND_TRAILING      # 默认近10年
    patched = client.patch("/api/report-settings", json={"model_kind": "since_inception"}).json()
    assert patched["model_kind"] == "since_inception"
    assert client.patch("/api/report-settings", json={"model_kind": "bogus"}).status_code == 400
    client.patch("/api/report-settings", json={"model_kind": "trailing_120m"})


def test_unknown_index_and_model(client):
    assert client.get("/api/indices/000905/history").status_code == 404
    assert client.get("/api/indices/000300/chart?model=nope").status_code == 404
    assert client.get("/api/indices/000300/status?model=weird").status_code == 400


def test_refresh_with_mocked_provider(client, service, monkeypatch, monthly_fixture):
    """POST /api/refresh：mock 供应商返回 fixture 数据，端到端刷新成功。"""
    from src.data import provider as pv

    rows = monthly_fixture["rows"]
    monthly_bars = [
        KlineBar(date=r["date"], open=r["open"], close=r["close"], high=r["high"], low=r["low"])
        for r in rows
    ] + [KlineBar(date="2026-10-28", open=4000.0, close=4060.0, high=4070.0, low=3980.0)]
    daily = [KlineBar(date="2026-10-28", open=4000.0, close=4050.0, high=4060.0, low=3990.0)]

    monkeypatch.setattr(pv, "fetch_kline", lambda symbol, period, count, client_: monthly_bars if period == "month" else daily)
    resp = client.post("/api/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data_cutoff_month"] == "2026-09"
    assert body["monthly_count"] == 258


def test_refresh_provider_failure_visible(client, service, monkeypatch):
    from src.data import provider as pv

    def boom(symbol, period, count, client_):
        raise pv.ProviderError("腾讯行情 HTTP 503")

    monkeypatch.setattr(pv, "fetch_kline", boom)
    resp = client.post("/api/refresh")
    assert resp.status_code == 502
    assert "腾讯行情" in resp.json()["detail"]
