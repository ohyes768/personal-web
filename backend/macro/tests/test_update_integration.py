"""Real HTTP endpoints, CSV persistence and both scheduler job histories.

Only external data sources are replaced. The pipeline, DataService, FastAPI
serialization, scheduler group execution and JSONL history remain real.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.scheduler import jobs
from src.scheduler.manager import SchedulerManager
from src.services import data_service as ds_module
from src.services.data_service import DataService
from src.services.update_registry import UPDATE_SPECS
from src.services.vix_service import VIXService

SOURCE_DATE = pd.Timestamp.now().normalize() - pd.Timedelta(days=2)


def series(value):
    return pd.Series([value], index=[SOURCE_DATE])


class FredSource:
    async def fetch_series(self, code, *_args):
        values = {"vix": 18.5, "tga": 712000.0, "sofr": 5.3, "us_3m": 4.9}
        key = next(key for key in values if routes.settings.fred_codes[key] == code)
        return series(values[key])


class HiborSource:
    async def fetch_series(self, *_args):
        return series(2.3)


class RateSource:
    def __init__(self, key):
        self.key = key

    async def fetch_latest(self, *_args):
        return pd.DataFrame({"date": [SOURCE_DATE], self.key: [1.23]})


class MarketSource:
    def fetch_today(self):
        return {
            "status": "ok",
            "date": SOURCE_DATE.strftime("%Y-%m-%d"),
            "total_amount_yi": 12345.0,
            "turnover_rate": 1.56,
            "rzye": 18888.0,
            "volume": pd.DataFrame(
                {"date": [SOURCE_DATE], "total_amount_yi": [12345.0]}
            ),
            "turnover": pd.DataFrame({"date": [SOURCE_DATE], "turnover_rate": [1.56]}),
        }


class FundFlowSource:
    def fetch_recent(self, **_kwargs):
        return {
            "north": pd.DataFrame({"北向成交额": [1000.0]}, index=[SOURCE_DATE]),
            "south": pd.DataFrame(
                {"南向净流入": [10.0], "南向买入": [50.0], "南向卖出": [40.0]},
                index=[SOURCE_DATE],
            ),
        }


class ChinaBondSource:
    def fetch_china_bond_yield(self, *_args):
        return pd.DataFrame(
            {"中国国债收益率10年": [1.8], "中国国债收益率10年-2年": [0.5]},
            index=[SOURCE_DATE],
        )


class KlineSource:
    def __init__(self, values):
        self.values = values

    async def fetch_all(self, *_args):
        return {key: series(value) for key, value in self.values.items()}


@pytest.fixture
def update_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(ds_module, "settings", SimpleNamespace(data_dir=str(tmp_path)))
    store = DataService()
    monkeypatch.setattr(routes, "_is_updating", False)
    monkeypatch.setattr(routes, "get_data_service", lambda: store)
    monkeypatch.setattr(routes, "get_fred_service", FredSource)
    monkeypatch.setattr(routes, "get_vix_service", VIXService)
    monkeypatch.setattr(routes, "get_hibor_service", HiborSource)
    monkeypatch.setattr(routes, "get_dr007_service", lambda: RateSource("dr007"))
    monkeypatch.setattr(routes, "get_dr001_service", lambda: RateSource("dr001"))
    monkeypatch.setattr(routes, "get_baostock_service", MarketSource)
    monkeypatch.setattr(routes, "get_margin_service", MarketSource)
    monkeypatch.setattr(routes, "get_fund_flow_service", FundFlowSource)
    monkeypatch.setattr(routes, "get_china_bond_service", ChinaBondSource)
    monkeypatch.setattr(
        routes,
        "get_commodity_service",
        lambda: KlineSource(
            {"gold": 650.0, "silver": 8.0, "oil": 70.0, "copper": 9000.0},
        ),
    )
    monkeypatch.setattr(
        routes,
        "get_index_service",
        lambda: KlineSource(
            {
                "HKHSI": 25000.0,
                "SH000001": 3800.0,
                "SPX": 6500.0,
                "IXIC": 22000.0,
                "DJI": 45000.0,
            },
        ),
    )

    async def fetch_us(*_args):
        return {
            key: series(value)
            for key, value in {
                "us_3m": 4.2,
                "us_2y": 3.7,
                "us_10y": 4.1,
            }.items()
        }

    async def fetch_oecd(*_args):
        return {
            key: series(value)
            for key, value in {
                "eu_3m": 2.1,
                "eu_2y_ecb": 2.2,
                "eu_10y": 2.5,
                "jp_10y": 1.1,
            }.items()
        }

    async def fetch_exchange(*_args):
        return {
            key: series(value)
            for key, value in {
                "dollar_index": 99.0,
                "usd_cny": 7.1,
                "usd_jpy": 150.0,
                "usd_eur": 0.9,
            }.items()
        }

    monkeypatch.setattr(routes, "_fetch_us_treasuries", fetch_us)
    monkeypatch.setattr(routes, "_fetch_oecd_bonds", fetch_oecd)
    monkeypatch.setattr(routes, "_fetch_exchange_rates", fetch_exchange)
    app = FastAPI()
    app.include_router(routes.router)
    yield SimpleNamespace(store=store, app=app, root=tmp_path)
    assert routes.is_updating() is False


def normalize_response(body):
    """Normalize only the response timestamp and two variable calendar dates."""
    result = dict(body)
    result.pop("updated_at", None)
    text = json.dumps(result)
    text = text.replace(SOURCE_DATE.strftime("%Y-%m-%d"), "<source-date>")
    text = text.replace(pd.Timestamp.now().strftime("%Y-%m-%d"), "<today>")
    return json.loads(text)


EXPECTED_FILES = {
    **{key: [key] for key in UPDATE_SPECS},
    "china_bonds": ["china_bond"],
    "legacy": ["us_treasuries", "eu_bonds", "jp_bonds", "exchange_rates"],
}


@pytest.mark.parametrize("key", list(UPDATE_SPECS))
def test_update_http_response_matches_pre_migration_contract_and_persists_csv(
    update_environment,
    key,
):
    environment = update_environment
    response = TestClient(environment.app).post("/api" + UPDATE_SPECS[key].endpoint)
    assert response.status_code == 200
    assert response.json()["success"] is True, response.json()
    baseline = json.loads(
        (Path(__file__).parent / "fixtures/update_success_responses.json").read_text(
            encoding="utf-8"
        ),
    )
    assert normalize_response(response.json()) == baseline[key]
    for name in EXPECTED_FILES[key]:
        data = pd.read_csv(environment.store.files[name], index_col=0, parse_dates=True)
        assert not data.empty
        assert data.index[-1].normalize() == SOURCE_DATE
        assert data.notna().any().any()


@pytest.mark.parametrize("job_id", ["a_share_daily", "global_daily"])
def test_scheduler_groups_execute_real_http_updates_and_record_csv_and_history(
    update_environment,
    monkeypatch,
    job_id,
):
    environment = update_environment
    config_path = Path(__file__).resolve().parents[1] / "src/scheduler/scheduler.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    manager = SchedulerManager(
        port=18094,
        config_path=config_path,
        history_path=environment.root / "scheduler/history.jsonl",
    )
    manager.jobs_meta = {job["id"]: job for job in config["jobs"]}
    original_async_client = httpx.AsyncClient
    responses = []

    async def capture(response):
        await response.aread()
        responses.append((response.request.url.path, response.json()))

    monkeypatch.setattr(
        jobs.httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(
            transport=httpx.ASGITransport(app=environment.app),
            event_hooks={"response": [capture]},
            **kwargs,
        ),
    )
    monkeypatch.setattr(jobs, "is_trading_day", lambda: True)
    asyncio.run(manager._run_job_wrapper(job_id))

    records = manager.get_job_runs(job_id)
    assert len(records) == 1
    record = records[0]
    targets = manager.jobs_meta[job_id]["targets"]
    assert record["status"] == "success", record
    assert record["count"] == len(targets)
    assert [item["path"] for item in record["items"]] == targets
    assert [path for path, _ in responses] == ["/api" + path for path in targets]
    for path, body in responses:
        assert body["success"] is True
        spec = next(
            spec for spec in UPDATE_SPECS.values() if "/api" + spec.endpoint == path
        )
        for name in EXPECTED_FILES[spec.key]:
            csv = pd.read_csv(
                environment.store.files[name], index_col=0, parse_dates=True
            )
            assert len(csv) == 1
            assert csv.index[-1].normalize() == SOURCE_DATE
