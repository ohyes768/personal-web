"""批 1：债券、行情与遗留总更新端点契约。"""
import os
os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.routes import router


class DataService:
    def __init__(self): self.saved = []
    def get_last_date(self, _key): return pd.Timestamp.now().normalize() - pd.Timedelta(days=2)
    def save_fred_data(self, *args, **kwargs): self.saved.append((args, kwargs))
    def save_commodities(self, data): self.saved.append(data)
    def save_indices(self, data): self.saved.append(data)
    def exchange_rates_need_aliyun_rebuild(self): return False


class KlineService:
    def __init__(self, value, failed=False): self.value, self.failed = value, failed
    async def fetch_all(self, *_args):
        if self.failed: raise RuntimeError("market source unavailable")
        return {"gold": pd.Series([self.value], index=[pd.Timestamp("2026-09-18")])}


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


@pytest.mark.parametrize(("path", "key", "prefix"), [
    ("/api/update/eu-bonds", "eu_treasuries", "eu_"),
    ("/api/update/jp-bonds", "jp_treasuries", "jp_"),
])
def test_oecd_update_persists_and_returns_payload(client, monkeypatch, path, key, prefix):
    data_service = DataService()
    async def fetch_oecd(*_args):
        return {f"{prefix}10y": pd.Series([2.5], index=[pd.Timestamp("2026-09-18")])}
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_oecd_bonds", fetch_oecd)

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert key in response.json()["data"]
    assert len(data_service.saved) == 1


@pytest.mark.parametrize(("path", "prefix"), [
    ("/api/update/eu-bonds", "eu_"),
    ("/api/update/jp-bonds", "jp_"),
])
def test_oecd_updates_use_the_shared_pipeline(client, monkeypatch, path, prefix):
    data_service = DataService()
    calls = []
    original_run = routes.UpdatePipeline.run

    async def recording_run(*args):
        calls.append(args)
        return await original_run(*args)

    async def fetch_oecd(*_args):
        return {f"{prefix}10y": pd.Series([2.5], index=[pd.Timestamp("2026-09-18")])}

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_oecd_bonds", fetch_oecd)
    monkeypatch.setattr(routes.UpdatePipeline, "run", recording_run)

    response = client.post(path)

    assert response.json()["success"] is True
    assert len(calls) == 1


@pytest.mark.parametrize("path", ["/api/update/eu-bonds", "/api/update/jp-bonds"])
def test_oecd_fetch_failure_does_not_persist(client, monkeypatch, path):
    data_service = DataService()
    async def fail_oecd(*_args): raise RuntimeError("OECD unavailable")
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_oecd_bonds", fail_oecd)

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert data_service.saved == []


@pytest.mark.parametrize(("path", "key", "service_name"), [
    ("/api/update/commodities", "commodities", "get_commodity_service"),
    ("/api/update/indices", "indices", "get_index_service"),
])
def test_kline_update_persists_and_returns_payload(client, monkeypatch, path, key, service_name):
    data_service = DataService()
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, service_name, lambda: KlineService(100.0))

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert key in response.json()["data"]
    assert len(data_service.saved) == 1


@pytest.mark.parametrize(("path", "service_name"), [
    ("/api/update/commodities", "get_commodity_service"),
    ("/api/update/indices", "get_index_service"),
])
def test_kline_updates_use_the_shared_pipeline(client, monkeypatch, path, service_name):
    data_service = DataService()
    calls = []
    original_run = routes.UpdatePipeline.run

    async def recording_run(*args):
        calls.append(args)
        return await original_run(*args)

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, service_name, lambda: KlineService(100.0))
    monkeypatch.setattr(routes.UpdatePipeline, "run", recording_run)

    response = client.post(path)

    assert response.json()["success"] is True
    assert len(calls) == 1


@pytest.mark.parametrize(("path", "service_name"), [
    ("/api/update/commodities", "get_commodity_service"),
    ("/api/update/indices", "get_index_service"),
])
def test_kline_fetch_failure_does_not_persist(client, monkeypatch, path, service_name):
    data_service = DataService()
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, service_name, lambda: KlineService(100.0, failed=True))

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert data_service.saved == []


def test_legacy_update_persists_fetched_data_and_returns_payload(client, monkeypatch):
    data_service = DataService()
    async def fetch_us(*_args): return {"us_3m": pd.Series([4.2], index=[pd.Timestamp("2026-09-18")])}
    async def fetch_oecd(*_args): return {"eu_10y": pd.Series([2.5], index=[pd.Timestamp("2026-09-18")])}
    async def fetch_exchange(*_args): return {"dollar_index": pd.Series([99.0], index=[pd.Timestamp("2026-09-18")])}
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", fetch_us)
    monkeypatch.setattr(routes, "_fetch_oecd_bonds", fetch_oecd)
    monkeypatch.setattr(routes, "_fetch_exchange_rates", fetch_exchange)

    response = client.post("/api/update")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"] is not None
    assert len(data_service.saved) == 2


def test_legacy_update_uses_the_shared_pipeline(client, monkeypatch):
    data_service = DataService()
    calls = []
    original_run = routes.UpdatePipeline.run

    async def recording_run(*args):
        calls.append(args)
        return await original_run(*args)

    async def fetch_us(*_args):
        return {"us_3m": pd.Series([4.2], index=[pd.Timestamp("2026-09-18")])}

    async def fetch_oecd(*_args):
        return {"eu_10y": pd.Series([2.5], index=[pd.Timestamp("2026-09-18")])}

    async def fetch_exchange(*_args):
        return {"dollar_index": pd.Series([99.0], index=[pd.Timestamp("2026-09-18")])}

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", fetch_us)
    monkeypatch.setattr(routes, "_fetch_oecd_bonds", fetch_oecd)
    monkeypatch.setattr(routes, "_fetch_exchange_rates", fetch_exchange)
    monkeypatch.setattr(routes.UpdatePipeline, "run", recording_run)

    response = client.post("/api/update")

    assert response.json()["success"] is True
    assert len(calls) == 1


def test_legacy_update_fetch_failure_does_not_persist(client, monkeypatch):
    data_service = DataService()
    async def fail_us(*_args): raise RuntimeError("FRED unavailable")
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", fail_us)

    response = client.post("/api/update")

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert data_service.saved == []
