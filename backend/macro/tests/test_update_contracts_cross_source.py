"""批 1：跨源更新端点的 HTTP / payload / 落库契约。"""
import os

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.routes import router


class RecordingDataService:
    def __init__(self): self.saved = []
    def get_last_date(self, _key): return pd.Timestamp.now().normalize() - pd.Timedelta(days=2)
    def exchange_rates_need_aliyun_rebuild(self): return False
    def save_fred_data(self, *args, **kwargs): self.saved.append((args, kwargs))
    def save_fund_flow(self, data): self.saved.append(data)
    def save_china_bond_data(self, data): self.saved.append(data)


class HiborService:
    def __init__(self, failed=False): self.failed = failed
    async def fetch_series(self, *_args):
        if self.failed: raise RuntimeError("HIBOR unavailable")
        return pd.Series([1.45], index=[pd.Timestamp("2026-09-18")])


class FundFlowService:
    def __init__(self, failed=False): self.failed = failed
    def fetch_recent(self, **_kwargs):
        if self.failed: raise RuntimeError("fund flow unavailable")
        index = pd.DatetimeIndex(["2026-09-18"])
        return {
            "north": pd.DataFrame({"北向成交额": [123.0]}, index=index),
            "south": pd.DataFrame({"南向净流入": [4.0], "南向买入": [8.0], "南向卖出": [4.0]}, index=index),
        }


class ChinaBondService:
    def __init__(self, failed=False): self.failed = failed
    def fetch_china_bond_yield(self, *_args):
        if self.failed: raise RuntimeError("bond source unavailable")
        return pd.DataFrame({
            "中国国债收益率10年": [2.1], "中国国债收益率10年-2年": [0.3],
        }, index=pd.DatetimeIndex(["2026-09-18"]))


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


def test_exchange_rates_persists_and_returns_exchange_payload(client, monkeypatch):
    data_service = RecordingDataService()
    async def fetch_exchange(*_args):
        return {key: pd.Series([value], index=[pd.Timestamp("2026-09-18")]) for key, value in {
            "dollar_index": 99.0, "usd_cny": 7.1, "usd_jpy": 150.0, "usd_eur": 0.9,
        }.items()}
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_exchange_rates", fetch_exchange)

    response = client.post("/api/update/exchange-rates")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["exchange_rates"]["dollar_index"]["value"] == 99.0
    assert len(data_service.saved) == 1


@pytest.mark.parametrize(
    ("path", "service_name", "service"),
    [
        ("/api/update/exchange-rates", None, None),
        ("/api/update/hibor", "get_hibor_service", HiborService()),
    ],
)
def test_single_series_cross_source_updates_use_the_shared_pipeline(
    client, monkeypatch, path, service_name, service
):
    data_service = RecordingDataService()
    calls = []
    original_run = routes.UpdatePipeline.run

    async def recording_run(*args):
        calls.append(args)
        return await original_run(*args)

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    if path.endswith("exchange-rates"):
        async def fetch_exchange(*_args):
            return {key: pd.Series([value], index=[pd.Timestamp("2026-09-18")]) for key, value in {
                "dollar_index": 99.0, "usd_cny": 7.1, "usd_jpy": 150.0, "usd_eur": 0.9,
            }.items()}
        monkeypatch.setattr(routes, "_fetch_exchange_rates", fetch_exchange)
    else:
        monkeypatch.setattr(routes, service_name, lambda: service)
    monkeypatch.setattr(routes.UpdatePipeline, "run", recording_run)

    response = client.post(path)

    assert response.json()["success"] is True
    assert len(calls) == 1


def test_exchange_rates_fetch_failure_does_not_persist(client, monkeypatch):
    data_service = RecordingDataService()
    async def fail_exchange(*_args): raise RuntimeError("exchange source unavailable")
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "_fetch_exchange_rates", fail_exchange)

    response = client.post("/api/update/exchange-rates")

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert data_service.saved == []


@pytest.mark.parametrize(("path", "key", "service_name", "service"), [
    ("/api/update/hibor", "hibor", "get_hibor_service", HiborService()),
    ("/api/update/fund-flow", "fund_flow", "get_fund_flow_service", FundFlowService()),
    ("/api/update/china-bonds", "china_bond_10y", "get_china_bond_service", ChinaBondService()),
])
def test_cross_source_updates_persist_and_return_payload(client, monkeypatch, path, key, service_name, service):
    data_service = RecordingDataService()
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, service_name, lambda: service)

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert key in response.json()["data"]
    assert len(data_service.saved) == 1


def test_fund_flow_update_uses_the_shared_pipeline(client, monkeypatch):
    data_service = RecordingDataService()
    calls = []
    original_run = routes.UpdatePipeline.run

    async def recording_run(*args):
        calls.append(args)
        return await original_run(*args)

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_fund_flow_service", lambda: FundFlowService())
    monkeypatch.setattr(routes.UpdatePipeline, "run", recording_run)

    response = client.post("/api/update/fund-flow")

    assert response.json()["success"] is True
    assert len(calls) == 1


def test_china_bonds_update_uses_the_shared_pipeline(client, monkeypatch):
    data_service = RecordingDataService()
    calls = []
    original_run = routes.UpdatePipeline.run

    async def recording_run(*args):
        calls.append(args)
        return await original_run(*args)

    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_china_bond_service", lambda: ChinaBondService())
    monkeypatch.setattr(routes.UpdatePipeline, "run", recording_run)

    response = client.post("/api/update/china-bonds")

    assert response.json()["success"] is True
    assert len(calls) == 1


@pytest.mark.parametrize(("path", "service_name", "service"), [
    ("/api/update/hibor", "get_hibor_service", HiborService(failed=True)),
    ("/api/update/fund-flow", "get_fund_flow_service", FundFlowService(failed=True)),
    ("/api/update/china-bonds", "get_china_bond_service", ChinaBondService(failed=True)),
])
def test_cross_source_fetch_failure_does_not_persist(client, monkeypatch, path, service_name, service):
    data_service = RecordingDataService()
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, service_name, lambda: service)

    response = client.post(path)

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert data_service.saved == []
