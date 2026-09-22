"""批 1：A 股更新端点的 HTTP / payload / 落库契约。"""
import os

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.routes import router


class RecordingDataService:
    def __init__(self):
        self.saved = []

    def get_last_date(self, _key):
        return pd.Timestamp.now().normalize() - pd.Timedelta(days=2)

    def save_dr007_data(self, data): self.saved.append(data)
    def save_dr001_data(self, data): self.saved.append(data)
    def save_volume_data(self, data): self.saved.append(data)
    def save_turnover_data(self, data): self.saved.append(data)
    def save_margin_data(self, data): self.saved.append(data)


class RateService:
    def __init__(self, key): self.key = key
    async def fetch_latest(self, *_args):
        return pd.DataFrame({"date": [pd.Timestamp("2026-09-18")], self.key: [1.23]})


class FailingRateService:
    async def fetch_latest(self, *_args):
        raise RuntimeError("rate source down")


class MarketService:
    def __init__(self, failed=False): self.failed = failed
    def fetch_today(self):
        return {
            "status": "failed" if self.failed else "ok", "error": "source down",
            "date": "2026-09-18", "total_amount_yi": 12345.0,
            "turnover_rate": 1.56, "rzye": 18888.0,
            "volume": pd.DataFrame({"date": ["2026-09-18"]}),
            "turnover": pd.DataFrame({"date": ["2026-09-18"]}),
        }


@pytest.fixture(autouse=True)
def reset_update_lock():
    routes._is_updating = False
    yield
    routes._is_updating = False


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize(("path", "key", "factory"), [
    ("/api/update/dr007", "dr007", lambda: RateService("dr007")),
    ("/api/update/dr001", "dr001", lambda: RateService("dr001")),
])
def test_rate_updates_persist_and_return_payload(client, monkeypatch, path, key, factory):
    data_service = RecordingDataService()
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_dr007_service", factory)
    monkeypatch.setattr(routes, "get_dr001_service", factory)

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"][key]["value"] == 1.23
    assert len(data_service.saved) == 1


@pytest.mark.parametrize("path", ["/api/update/dr007", "/api/update/dr001"])
def test_rate_updates_use_the_shared_pipeline(client, monkeypatch, path):
    data_service = RecordingDataService()
    calls = []
    original_run = routes.UpdatePipeline.run

    async def recording_run(*args):
        calls.append(args)
        return await original_run(*args)

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_dr007_service", lambda: RateService("dr007"))
    monkeypatch.setattr(routes, "get_dr001_service", lambda: RateService("dr001"))
    monkeypatch.setattr(routes.UpdatePipeline, "run", recording_run)

    response = client.post(path)

    assert response.json()["success"] is True
    assert len(calls) == 1


@pytest.mark.parametrize("path", ["/api/update/dr007", "/api/update/dr001"])
def test_rate_update_fetch_failure_does_not_persist(client, monkeypatch, path):
    data_service = RecordingDataService()
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_dr007_service", lambda: FailingRateService())
    monkeypatch.setattr(routes, "get_dr001_service", lambda: FailingRateService())

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert data_service.saved == []


@pytest.mark.parametrize(("path", "key"), [
    ("/api/update/volume", "volume"),
    ("/api/update/turnover", "turnover"),
    ("/api/update/margin", "margin"),
])
def test_market_updates_persist_and_return_payload(client, monkeypatch, path, key):
    data_service = RecordingDataService()
    market = MarketService()
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_baostock_service", lambda: market)
    monkeypatch.setattr(routes, "get_margin_service", lambda: market)

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"][key]["value"] is not None
    assert len(data_service.saved) == 1


@pytest.mark.parametrize("path", ["/api/update/volume", "/api/update/turnover", "/api/update/margin"])
def test_market_updates_use_the_shared_pipeline(client, monkeypatch, path):
    data_service = RecordingDataService()
    calls = []
    original_run = routes.UpdatePipeline.run

    async def recording_run(*args):
        calls.append(args)
        return await original_run(*args)

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_baostock_service", lambda: MarketService())
    monkeypatch.setattr(routes, "get_margin_service", lambda: MarketService())
    monkeypatch.setattr(routes.UpdatePipeline, "run", recording_run)

    response = client.post(path)

    assert response.json()["success"] is True
    assert len(calls) == 1


@pytest.mark.parametrize("path", ["/api/update/volume", "/api/update/turnover", "/api/update/margin"])
def test_market_update_fetch_failure_does_not_persist(client, monkeypatch, path):
    data_service = RecordingDataService()
    market = MarketService(failed=True)
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_baostock_service", lambda: market)
    monkeypatch.setattr(routes, "get_margin_service", lambda: market)

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert data_service.saved == []
