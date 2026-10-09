"""更新管道与注册表的完整性契约。"""

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import get_args, get_type_hints

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.routes import router
from src.models import UpdateResponse
from src.services.update_pipeline import UpdatePipeline
from src.services.update_registry import UPDATE_SPECS


def test_us_treasuries_is_registered_for_the_update_pipeline():
    spec = UPDATE_SPECS["us_treasuries"]

    assert spec.endpoint == "/update/us-treasuries"
    assert spec.payload_type.__name__ == "USTreasuriesUpdateData"


def test_market_update_specs_expose_executable_stage_builders():
    for key in ("volume", "turnover", "margin"):
        assert callable(UPDATE_SPECS[key].build_stages)


@pytest.mark.parametrize("key", list(UPDATE_SPECS))
def test_every_update_spec_exposes_an_executable_stage_builder(key):
    assert callable(UPDATE_SPECS[key].build_stages)


@pytest.mark.parametrize("key", list(UPDATE_SPECS))
def test_http_update_invokes_its_registered_builder_and_releases_lock(key, monkeypatch):
    spec = UPDATE_SPECS[key]
    calls = []

    def failing_builder(*args):
        calls.append(key)
        raise RuntimeError("registered builder failed")

    monkeypatch.setitem(UPDATE_SPECS, key, replace(spec, build_stages=failing_builder))
    monkeypatch.setattr(routes, "_is_updating", False)
    # The builder should run before any real data source is opened.
    monkeypatch.setattr(routes, "get_data_service", lambda: None)
    monkeypatch.setattr(routes, "get_fred_service", lambda: None)
    monkeypatch.setattr(routes, "get_vix_service", lambda: None)
    monkeypatch.setattr(routes, "get_hibor_service", lambda: None)
    monkeypatch.setattr(routes, "get_dr007_service", lambda: None)
    monkeypatch.setattr(routes, "get_dr001_service", lambda: None)
    monkeypatch.setattr(routes, "get_baostock_service", lambda: None)
    monkeypatch.setattr(routes, "get_margin_service", lambda: None)
    monkeypatch.setattr(routes, "get_fund_flow_service", lambda: None)
    monkeypatch.setattr(routes, "get_china_bond_service", lambda: None)
    monkeypatch.setattr(routes, "get_commodity_service", lambda: None)
    monkeypatch.setattr(routes, "get_index_service", lambda: None)
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).post("/api" + spec.endpoint)

    assert calls == [key]
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "UPDATE_FAILED"
    assert "registered builder failed" in response.json()["message"]
    assert routes.is_updating() is False


def test_registry_has_one_unique_spec_for_every_incremental_update_endpoint():
    assert len(UPDATE_SPECS) == 18
    assert len({spec.endpoint for spec in UPDATE_SPECS.values()}) == 18


def test_registry_paths_exactly_match_the_incremental_update_routes():
    registered_paths = {spec.endpoint for spec in UPDATE_SPECS.values()}
    routed_paths = {
        route.path.removeprefix("/api")
        for route in router.routes
        if route.path == "/api/update" or route.path.startswith("/api/update/")
    }

    assert registered_paths == routed_paths


def test_every_registered_payload_is_declared_by_update_response_and_has_a_contract_test():
    response_data_types = set(
        payload_type
        for payload_type in get_args(get_type_hints(UpdateResponse)["data"])
        if payload_type is not type(None)
    )
    tests_dir = Path(__file__).parent

    for spec in UPDATE_SPECS.values():
        assert spec.payload_type in response_data_types
        assert (tests_dir / spec.contract_test_file).is_file()


def test_pipeline_runs_fetch_validate_save_and_payload_in_order():
    events = []

    async def fetch():
        events.append("fetch")
        return 1

    def validate(value):
        events.append("validate")
        return value + 1

    def save(value):
        events.append(("save", value))

    def payload(value):
        events.append(("payload", value))
        return {"value": value}

    result = asyncio.run(UpdatePipeline.run(fetch, validate, save, payload))

    assert result == {"value": 2}
    assert events == ["fetch", "validate", ("save", 2), ("payload", 2)]
