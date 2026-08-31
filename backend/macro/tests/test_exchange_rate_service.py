"""汇率切到阿里云 comkm：symbol 映射、EUR 取倒数、全量覆盖、禁止混写 FRED 广义美元指数。"""
from __future__ import annotations

import asyncio
import os
from datetime import date
from pathlib import Path

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.routes import router
from src.services import data_service as ds_mod
from src.services.data_service import DataService
from src.services.exchange_rate_service import ExchangeRateService


def _make_service(tmp_path: Path) -> DataService:
    service = DataService()
    service.data_dir = tmp_path
    service.files = {key: tmp_path / path.name for key, path in service.files.items()}
    with ds_mod._QUERY_CACHE_LOCK:
        ds_mod._QUERY_CACHE.clear()
    ds_mod._bump_cache_version()
    return service


@pytest.mark.unit
def test_fetch_all_maps_comkm_symbols_and_inverts_eurusd(monkeypatch):
    monkeypatch.setattr(
        "src.services.exchange_rate_service.settings.aliyun_api_appcode",
        "test-appcode",
    )
    closes = {"DXY": 99.68, "USDCNY": 6.7349, "USDJPY": 160.093, "EURUSD": 1.15816}
    requested: list[str] = []

    async def fake_klines(client, *, base_url, symbol, logger, since=None):
        requested.append(symbol)
        return [{"date": pd.Timestamp("2026-08-28"), "close": closes[symbol]}]

    monkeypatch.setattr(
        "src.services.exchange_rate_service.fetch_comkm_klines", fake_klines
    )

    result = asyncio.run(ExchangeRateService.fetch_all(date(2026, 8, 1), date(2026, 8, 31)))

    assert set(requested) == {"DXY", "USDCNY", "USDJPY", "EURUSD"}
    assert result["dollar_index"].iloc[0] == pytest.approx(99.68)
    assert result["usd_cny"].iloc[0] == pytest.approx(6.7349)
    assert result["usd_jpy"].iloc[0] == pytest.approx(160.093)
    assert result["usd_eur"].iloc[0] == pytest.approx(1 / 1.15816)


@pytest.mark.unit
def test_fetch_all_without_appcode_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "src.services.exchange_rate_service.settings.aliyun_api_appcode",
        "",
    )
    result = asyncio.run(ExchangeRateService.fetch_all(date(2026, 8, 1), date(2026, 8, 31)))
    assert result == {}


@pytest.mark.unit
def test_save_exchange_rates_replace_drops_fred_history(tmp_path):
    service = _make_service(tmp_path)
    old = pd.Series(
        [118.2, 118.1],
        index=pd.to_datetime(["2026-08-20", "2026-08-21"]),
        name="dollar_index",
    )
    service.save_fred_data({"dollar_index": old}, key="exchange_rates")
    assert service.exchange_rates_need_aliyun_rebuild() is True

    new = pd.Series([99.68], index=pd.to_datetime(["2026-08-28"]), name="dollar_index")
    service.save_fred_data({"dollar_index": new}, key="exchange_rates", replace=True)

    loaded = service.load_data("exchange_rates")
    assert list(loaded.index.strftime("%Y-%m-%d")) == ["2026-08-28"]
    assert loaded["美元指数"].iloc[0] == pytest.approx(99.68)
    assert service.exchange_rates_need_aliyun_rebuild() is False


@pytest.fixture(autouse=True)
def _reset_lock():
    routes._is_updating = False
    yield
    routes._is_updating = False


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class _FakeDs:
    def __init__(self, *, need_rebuild: bool, last_date):
        self._need_rebuild = need_rebuild
        self._last_date = last_date
        self.saved = False
        self.replace_used = None

    def get_last_date(self, _data_type):
        return self._last_date

    def exchange_rates_need_aliyun_rebuild(self):
        return self._need_rebuild

    def save_fred_data(self, *_a, **kwargs):
        self.saved = True
        self.replace_used = kwargs.get("replace", False)


def test_update_exchange_rates_rejects_fred_scale_csv(client, monkeypatch):
    ds = _FakeDs(need_rebuild=True, last_date=pd.Timestamp("2026-08-21"))
    monkeypatch.setattr(routes, "get_data_service", lambda: ds)

    async def should_not_fetch(*_a, **_k):
        raise AssertionError("FRED 口径底库不得增量拉取")

    monkeypatch.setattr(routes, "_fetch_exchange_rates", should_not_fetch)

    res = client.post("/api/update/exchange-rates")
    body = res.json()
    assert body["success"] is False
    assert body["error_code"] == "UPDATE_FAILED"
    assert "history" in body["message"]
    assert ds.saved is False


def test_fetch_exchange_rates_history_replaces_csv(client, monkeypatch):
    ds = _FakeDs(need_rebuild=True, last_date=pd.Timestamp("2026-08-21"))
    series = pd.Series([99.68], index=pd.to_datetime(["2026-08-28"]))

    async def fake_fetch(*_a, **_k):
        return {
            "dollar_index": series,
            "usd_cny": series,
            "usd_jpy": series,
            "usd_eur": series,
        }

    monkeypatch.setattr(routes, "get_data_service", lambda: ds)
    monkeypatch.setattr(routes, "_fetch_exchange_rates", fake_fetch)

    res = client.post("/api/fetch/exchange-rates/history")
    body = res.json()
    assert body["success"] is True
    assert ds.saved is True
    assert ds.replace_used is True
