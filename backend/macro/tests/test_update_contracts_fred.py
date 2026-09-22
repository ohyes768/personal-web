"""批 1：FRED 更新端点的 HTTP / payload / 落库契约。"""
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

    def save_fred_data(self, *args, **kwargs):
        self.saved.append((args, kwargs))

    def save_ted_spread_data(self, *args, **kwargs):
        self.saved.append((args, kwargs))


class PassthroughVixService:
    def convert_timezone(self, series):
        return series

    def validate_data(self, series):
        return series

    def normalize_data(self, series):
        return series


class FredSeries:
    def __init__(self, values):
        self.values = values

    async def fetch_series(self, _code, _start, _end):
        return next(self.values)


class FailingFred:
    async def fetch_series(self, *_args):
        raise RuntimeError("FRED unavailable")


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


def series(value):
    return pd.Series([value], index=[pd.Timestamp("2026-09-18")])


def test_update_us_treasuries_persists_and_returns_treasury_payload(client, monkeypatch):
    data_service = RecordingDataService()

    async def fetch_us_treasuries(*_args):
        return {"us_3m": series(4.2), "us_2y": series(3.7), "us_10y": series(4.1)}

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", fetch_us_treasuries)

    response = client.post("/api/update/us-treasuries")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["us_treasuries"]["y10"]["value"] == 4.1
    assert len(data_service.saved) == 1


def test_update_us_treasuries_fetch_failure_does_not_persist(client, monkeypatch):
    data_service = RecordingDataService()

    async def fetch_us_treasuries(*_args):
        raise RuntimeError("FRED unavailable")

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", fetch_us_treasuries)

    response = client.post("/api/update/us-treasuries")

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert data_service.saved == []


@pytest.mark.parametrize(
    ("path", "payload_key", "fred_values"),
    [
        ("/api/update/vix", "vix", [18.5]),
        ("/api/update/tga", "tga", [712.0]),
        ("/api/update/ted-spread", "ted_spread", [5.3, 4.9]),
    ],
)
def test_fred_updates_persist_and_return_declared_payload(client, monkeypatch, path, payload_key, fred_values):
    data_service = RecordingDataService()
    values = iter(series(value) for value in fred_values)
    fred = FredSeries(values)

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_fred_service", lambda: fred)
    monkeypatch.setattr(routes, "get_vix_service", lambda: PassthroughVixService())

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert payload_key in response.json()["data"]
    assert len(data_service.saved) == 1


@pytest.mark.parametrize(
    ("path", "fred_values"),
    [
        ("/api/update/vix", [18.5]),
        ("/api/update/tga", [712.0]),
        ("/api/update/ted-spread", [5.3, 4.9]),
    ],
)
def test_fred_updates_use_the_shared_pipeline(client, monkeypatch, path, fred_values):
    data_service = RecordingDataService()
    calls = []
    original_run = routes.UpdatePipeline.run

    async def recording_run(*args):
        calls.append(args)
        return await original_run(*args)

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_fred_service", lambda: FredSeries(iter(series(value) for value in fred_values)))
    monkeypatch.setattr(routes, "get_vix_service", lambda: PassthroughVixService())
    monkeypatch.setattr(routes.UpdatePipeline, "run", recording_run)

    response = client.post(path)

    assert response.json()["success"] is True
    assert len(calls) == 1


@pytest.mark.parametrize("path", ["/api/update/vix", "/api/update/tga", "/api/update/ted-spread"])
def test_fred_update_fetch_failure_does_not_persist(client, monkeypatch, path):
    data_service = RecordingDataService()

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_fred_service", lambda: FailingFred())
    monkeypatch.setattr(routes, "get_vix_service", lambda: PassthroughVixService())

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert data_service.saved == []
