"""估值在状态 API 中的呈现：只读缓存、不在 GET 内请求供应商、缺服务可降级。"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import router
from src.data import lixinger as lx
from src.services.trend_service import WeeklyTrendService
from src.services.valuation_service import ValuationService

from tests.conftest import WEEKLY_FIXED_NOW


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


@pytest.fixture()
def valuation_client():
    return _FakeClient(_payload())


@pytest.fixture()
def api_app(store, weekly_series, weekly_daily_bars, valuation_client):
    service = WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)
    service.publish(weekly_series, weekly_daily_bars, service.compute_models(weekly_series))
    valuation = ValuationService(
        store,
        token="token",
        calendar=service.trading_calendar,
        now_fn=lambda: WEEKLY_FIXED_NOW,
        client_factory=lambda: valuation_client,
    )
    valuation.refresh()
    app = FastAPI()
    app.include_router(router)
    app.state.trend_service = service
    app.state.valuation_service = valuation
    app.state.store = store
    return app


@pytest.fixture()
def client(api_app):
    with TestClient(api_app) as test_client:
        yield test_client


def test_status_includes_valuation(client):
    body = client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    valuation = body["valuation"]
    assert valuation["state"] == "ok"
    assert valuation["percentile_pct"] == 56.6
    assert valuation["pe_ttm"] == 12.35
    assert valuation["source"] == "lixinger"
    assert valuation["window"] == "y10"
    assert valuation["as_of"] == "2026-10-30"


def test_status_valuation_is_shared_between_models(client):
    first = client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    second = client.get("/api/indices/000300/status?model=since_inception_weekly").json()
    assert first["valuation"] == second["valuation"]


def test_status_does_not_request_provider(client, valuation_client):
    before = valuation_client.calls
    client.get("/api/indices/000300/status?model=trailing_10y_weekly")
    assert valuation_client.calls == before


def test_status_never_leaks_token(client):
    body = client.get("/api/indices/000300/status?model=trailing_10y_weekly").text
    assert "token" not in body.lower()


def test_status_without_valuation_service_degrades(store, weekly_series, weekly_daily_bars):
    service = WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)
    service.publish(weekly_series, weekly_daily_bars, service.compute_models(weekly_series))
    app = FastAPI()
    app.include_router(router)
    app.state.trend_service = service
    with TestClient(app) as test_client:
        body = test_client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    assert body["valuation"]["state"] == "disabled"
    assert body["valuation"]["percentile_pct"] is None


def test_status_with_disabled_valuation_service(store, weekly_series, weekly_daily_bars):
    service = WeeklyTrendService(store, now_fn=lambda: WEEKLY_FIXED_NOW)
    service.publish(weekly_series, weekly_daily_bars, service.compute_models(weekly_series))
    valuation = ValuationService(store, token="", calendar=service.trading_calendar)
    app = FastAPI()
    app.include_router(router)
    app.state.trend_service = service
    app.state.valuation_service = valuation
    with TestClient(app) as test_client:
        body = test_client.get("/api/indices/000300/status?model=trailing_10y_weekly").json()
    assert body["valuation"]["state"] == "disabled"
    assert body["valuation"]["reason"] == "token_not_configured"
