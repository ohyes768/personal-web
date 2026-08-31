"""增量空窗：API 成功无新观测且已有 last_date → 已是最新；真失败上抛原文。"""
import os

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.routes import _empty_increment_is_current, _has_observations, router


def _empty_series() -> pd.Series:
    return pd.Series(dtype="float64")


class FakeDataService:
    def __init__(self, last_date):
        self._last_date = last_date
        self.saved = False

    def get_last_date(self, _data_type):
        return self._last_date

    def save_fred_data(self, *_a, **_k):
        self.saved = True

    def save_china_bond_data(self, *_a, **_k):
        self.saved = True

    def save_ted_spread_data(self, *_a, **_k):
        self.saved = True

    def save_commodities(self, *_a, **_k):
        self.saved = True

    def save_indices(self, *_a, **_k):
        self.saved = True


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


def test_has_observations_dict_and_empty_series():
    assert not _has_observations({})
    assert not _has_observations(_empty_series())
    assert not _has_observations({"a": _empty_series()})
    s = pd.Series([1.2], index=[pd.Timestamp("2026-08-28")])
    assert _has_observations(s)
    assert _has_observations({"a": s})


def test_empty_increment_is_current():
    as_of = pd.Timestamp("2026-08-31")
    assert _empty_increment_is_current(
        FakeDataService(pd.Timestamp("2026-08-27")), "us_treasuries", as_of=as_of
    )
    assert _empty_increment_is_current(
        FakeDataService(pd.Timestamp("2026-08-26")), "tga", as_of=as_of
    )
    assert not _empty_increment_is_current(FakeDataService(None), "us_treasuries", as_of=as_of)
    # 汇率底库停在 8-21、今天 8-31：空窗不得当成已是最新
    assert not _empty_increment_is_current(
        FakeDataService(pd.Timestamp("2026-08-21")), "exchange_rates", as_of=as_of
    )


def test_us_treasuries_empty_window_is_current(client, monkeypatch):
    ds = FakeDataService(pd.Timestamp.now().normalize() - pd.Timedelta(days=2))

    async def empty_fetch(*_a, **_k):
        return {"us_3m": _empty_series(), "us_2y": _empty_series(), "us_10y": _empty_series()}

    monkeypatch.setattr(routes, "get_data_service", lambda: ds)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", empty_fetch)

    res = client.post("/api/update/us-treasuries")
    body = res.json()
    assert res.status_code == 200
    assert body["success"] is True
    assert "已是最新" in body["message"]
    assert ds.saved is False


def test_us_treasuries_fred_error_propagates(client, monkeypatch):
    ds = FakeDataService(pd.Timestamp.now().normalize() - pd.Timedelta(days=2))

    async def boom(*_a, **_k):
        raise RuntimeError("fred down")

    monkeypatch.setattr(routes, "get_data_service", lambda: ds)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", boom)

    res = client.post("/api/update/us-treasuries")
    body = res.json()
    assert body["success"] is False
    assert body["error_code"] == "UPDATE_FAILED"
    assert "fred down" in body["message"]
    assert ds.saved is False


def test_us_treasuries_empty_without_csv_fails(client, monkeypatch):
    ds = FakeDataService(None)

    async def empty_fetch(*_a, **_k):
        return {"us_3m": _empty_series(), "us_2y": _empty_series(), "us_10y": _empty_series()}

    monkeypatch.setattr(routes, "get_data_service", lambda: ds)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", empty_fetch)

    res = client.post("/api/update/us-treasuries")
    body = res.json()
    assert body["success"] is False
    assert "未能获取到任何美债新数据" in body["message"]


def test_us_treasuries_empty_window_stale_fails(client, monkeypatch):
    """底库 last_date 落后超过允许空窗天数：API 空观测不得标成已是最新。"""
    ds = FakeDataService(pd.Timestamp.now().normalize() - pd.Timedelta(days=10))

    async def empty_fetch(*_a, **_k):
        return {"us_3m": _empty_series(), "us_2y": _empty_series(), "us_10y": _empty_series()}

    monkeypatch.setattr(routes, "get_data_service", lambda: ds)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", empty_fetch)

    res = client.post("/api/update/us-treasuries")
    body = res.json()
    assert body["success"] is False
    assert body["error_code"] == "UPDATE_FAILED"
    assert "未能获取到任何美债新数据" in body["message"]
    assert "落后" in body["message"]
    assert ds.saved is False


def test_exchange_rates_empty_window_stale_fails(client, monkeypatch):
    ds = FakeDataService(pd.Timestamp.now().normalize() - pd.Timedelta(days=10))

    async def empty_fetch(*_a, **_k):
        return {
            "dollar_index": _empty_series(),
            "usd_cny": _empty_series(),
            "usd_jpy": _empty_series(),
            "usd_eur": _empty_series(),
        }

    monkeypatch.setattr(routes, "get_data_service", lambda: ds)
    monkeypatch.setattr(routes, "_fetch_exchange_rates", empty_fetch)

    res = client.post("/api/update/exchange-rates")
    body = res.json()
    assert body["success"] is False
    assert "未能获取到任何汇率新数据" in body["message"]
    assert "落后" in body["message"]
    assert ds.saved is False


def test_us_treasuries_history_empty_still_fails(client, monkeypatch):
    ds = FakeDataService(pd.Timestamp("2026-08-01"))

    async def empty_fetch(*_a, **_k):
        return {"us_3m": _empty_series(), "us_2y": _empty_series(), "us_10y": _empty_series()}

    monkeypatch.setattr(routes, "get_data_service", lambda: ds)
    monkeypatch.setattr(routes, "_fetch_us_treasuries", empty_fetch)

    res = client.post("/api/fetch/us-treasuries/history")
    body = res.json()
    assert body["success"] is False
    assert "未能获取到任何美债数据" in body["message"]


def _past_last():
    return pd.Timestamp.now().normalize() - pd.Timedelta(days=2)


def _async_empty_dict(keys):
    async def _fn(*_a, **_k):
        return {k: _empty_series() for k in keys}

    return _fn


class _FredEmpty:
    async def fetch_series(self, *_a, **_k):
        return _empty_series()


class _SeriesEmpty:
    async def fetch_series(self, *_a, **_k):
        return _empty_series()


class _ChinaEmpty:
    def fetch_china_bond_yield(self, *_a, **_k):
        return pd.DataFrame()


class _DictEmpty:
    def __init__(self, keys):
        self.keys = keys

    async def fetch_all(self, *_a, **_k):
        return {k: _empty_series() for k in self.keys}


@pytest.mark.parametrize(
    "path,setup",
    [
        (
            "/api/update/exchange-rates",
            lambda mp, ds: (
                mp.setattr(routes, "get_data_service", lambda: ds),
                mp.setattr(
                    routes,
                    "_fetch_exchange_rates",
                    _async_empty_dict(["dollar_index", "usd_cny", "usd_jpy", "usd_eur"]),
                ),
            ),
        ),
        (
            "/api/update/vix",
            lambda mp, ds: (
                mp.setattr(routes, "get_data_service", lambda: ds),
                mp.setattr(routes, "get_fred_service", lambda: _FredEmpty()),
            ),
        ),
        (
            "/api/update/tga",
            lambda mp, ds: (
                mp.setattr(routes, "get_data_service", lambda: ds),
                mp.setattr(routes, "get_fred_service", lambda: _FredEmpty()),
            ),
        ),
        (
            "/api/update/hibor",
            lambda mp, ds: (
                mp.setattr(routes, "get_data_service", lambda: ds),
                mp.setattr(routes, "get_hibor_service", lambda: _SeriesEmpty()),
            ),
        ),
        (
            "/api/update/china-bonds",
            lambda mp, ds: (
                mp.setattr(routes, "get_data_service", lambda: ds),
                mp.setattr(routes, "get_china_bond_service", lambda: _ChinaEmpty()),
            ),
        ),
        (
            "/api/update/ted-spread",
            lambda mp, ds: (
                mp.setattr(routes, "get_data_service", lambda: ds),
                mp.setattr(routes, "get_fred_service", lambda: _FredEmpty()),
            ),
        ),
        (
            "/api/update/commodities",
            lambda mp, ds: (
                mp.setattr(routes, "get_data_service", lambda: ds),
                mp.setattr(routes, "get_commodity_service", lambda: _DictEmpty(["gold"])),
            ),
        ),
        (
            "/api/update/indices",
            lambda mp, ds: (
                mp.setattr(routes, "get_data_service", lambda: ds),
                mp.setattr(routes, "get_index_service", lambda: _DictEmpty(["SPX"])),
            ),
        ),
    ],
)
def test_other_increment_empty_window_is_current(client, monkeypatch, path, setup):
    ds = FakeDataService(_past_last())
    setup(monkeypatch, ds)
    res = client.post(path)
    body = res.json()
    assert res.status_code == 200
    assert body["success"] is True
    assert "已是最新" in body["message"]
    assert ds.saved is False


def test_update_in_progress(client):
    routes._is_updating = True
    res = client.post("/api/update/us-treasuries")
    body = res.json()
    assert body["success"] is False
    assert body["error_code"] == "UPDATE_IN_PROGRESS"
