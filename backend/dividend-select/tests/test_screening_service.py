import pytest
from src.api.models import DividendStock, ScreeningRequest
from src.services.screening_service import evaluate_stock


def stock(**updates):
    fields = dict(code="000001", name="样本", exchange="深市主板", avg_yield_3y=3.5,
                  dividend_2023=1, dividend_2024=1, dividend_2025=1,
                  roe=10, roe_avg_3y=10, roe_year=2025,
                  roe_history=[dict(year=y, value=10) for y in [2023, 2024, 2025]],
                  net_profit_ex_non_recurring_yoy=0, annual_net_profit_ex_non_recurring=100, annual_profit_year=2025,
                  latest_quarter_label="2026Q1", previous_quarter_label="2025Q4",
                  latest_quarter_yoy_pct=0, previous_quarter_yoy_pct=0)
    fields.update(updates)
    return DividendStock(**fields)


@pytest.mark.parametrize("previous,latest,status", [(-10,-5,"excluded"),(-10,2,"eligible"),(5,-10,"eligible"),(0,-10,"eligible"),(0,0,"eligible")])
def test_quarter_rule(previous, latest, status):
    result = evaluate_stock(stock(previous_quarter_yoy_pct=previous, latest_quarter_yoy_pct=latest), ScreeningRequest())
    assert result.status == status
    assert bool(result.warnings) == (status == "eligible" and min(previous, latest) < 0)


@pytest.mark.parametrize("updates", [dict(roe_avg_3y=None), dict(roe_history=[]), dict(roe_year=None), dict(previous_quarter_label="2025Q3"), dict(latest_quarter_yoy_pct=None), dict(dividend_2024=None)])
def test_missing_not_passed(updates):
    assert evaluate_stock(stock(**updates), ScreeningRequest()).status == "insufficient_data"


def test_boundary_annual_failure_and_priority():
    assert evaluate_stock(stock(), ScreeningRequest()).status == "eligible"
    assert evaluate_stock(stock(net_profit_ex_non_recurring_yoy=-1, roe_avg_3y=None), ScreeningRequest()).status == "excluded"
    assert evaluate_stock(stock(dividend_2024=0), ScreeningRequest()).status == "excluded"


def test_screen_route_loads_full_collected_pool(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import routes
    from src.api.models import StockListResponse
    calls = []
    async def load(**kwargs):
        calls.append(kwargs)
        return StockListResponse(total=2, items=[stock(), stock(code='000090', avg_yield_3y=1)], last_updated='2026-10-09')
    monkeypatch.setattr(routes, 'get_stocks', load)
    monkeypatch.setattr(routes, 'find_latest_aux_file', lambda *args: 'financial.csv')
    monkeypatch.setattr(routes, 'file_mtime_iso', lambda *args: '2026-10-10T01:00:00+08:00')
    app = FastAPI()
    app.include_router(routes.router)
    response = TestClient(app).post('/stocks/screen', json={})
    assert response.status_code == 200
    body = response.json()
    assert body['counts'] == {'eligible': 1, 'excluded': 1, 'insufficient_data': 0}
    assert body['conditions']['max_quarter_profit_decline_pct'] == 30
    assert body['items'][0]['stock']['annual_profit_year'] == 2025
    assert body['items'][0]['stock']['annual_net_profit_ex_non_recurring'] == 100
    assert body['total'] == 2
    assert body['financial_last_updated'] == '2026-10-10T01:00:00+08:00'
    assert calls[0] == dict(min_yield=0, max_yield=None, exchange=None, industry=None, index=None, sort_by='avg_yield_3y', sort_order='desc')
    assert TestClient(app).post('/stocks/screen', json={'min_roe': -1}).status_code == 422


def test_display_yield_does_not_filter():
    assert evaluate_stock(stock(yield_2025=0.1), ScreeningRequest()).status == 'eligible'
    assert evaluate_stock(stock(yield_2025=20), ScreeningRequest()).status == 'eligible'


def test_nonfinite_dividend_csv_values_are_json_safe():
    import pandas as pd
    from src.api.routes import _row_to_stock_model
    row = pd.Series({"股票代码": "000001", "股票名称": "测试", "3年平均股息率(%)": float("inf"), "2025年分红(元/股)": float("-inf")})
    result = _row_to_stock_model(row)
    assert result.avg_yield_3y is None
    assert result.dividend_2025 is None
    assert 'Infinity' not in result.model_dump_json()


@pytest.mark.parametrize("threshold,value,status", [(30,-30,"excluded"),(30,-29.99,"eligible"),(20,-20,"excluded"),(50,-30,"eligible"),(50,-50,"excluded")])
@pytest.mark.parametrize("quarter", ["latest", "previous"])
def test_single_quarter_decline_boundary(threshold, value, status, quarter):
    result = evaluate_stock(stock(**{f"{quarter}_quarter_yoy_pct": value}), ScreeningRequest(max_quarter_profit_decline_pct=threshold))
    assert result.status == status
    if status == "excluded":
        assert any(f"{threshold}%" in reason and ("2026Q1" if quarter == "latest" else "2025Q4") in reason for reason in result.reasons)


@pytest.mark.parametrize("value", [0, -10])
def test_annual_loss_cannot_pass_even_when_yoy_improves(value):
    result = evaluate_stock(stock(annual_net_profit_ex_non_recurring=value, net_profit_ex_non_recurring_yoy=50, latest_quarter_yoy_pct=None), ScreeningRequest())
    assert result.status == "excluded"
    assert any("2025" in reason and "大于 0" in reason for reason in result.reasons)


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), float("-inf")])
def test_missing_annual_amount(value):
    assert evaluate_stock(stock(annual_net_profit_ex_non_recurring=value), ScreeningRequest()).status == "insufficient_data"


def test_decline_failure_wins_missing_other_quarter():
    result = evaluate_stock(stock(latest_quarter_yoy_pct=-30, previous_quarter_yoy_pct=None), ScreeningRequest())
    assert result.status == "excluded"


@pytest.mark.parametrize("value", [0, -1, 101, float("nan"), float("inf")])
def test_decline_threshold_validation(value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ScreeningRequest(max_quarter_profit_decline_pct=value)


def test_nonadjacent_severe_quarter_stays_missing():
    assert evaluate_stock(stock(previous_quarter_label="2025Q3", previous_quarter_yoy_pct=-50), ScreeningRequest()).status == "insufficient_data"


def test_api_threshold_snapshot_and_validation(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import routes
    from src.api.models import StockListResponse
    async def load(**kwargs):
        return StockListResponse(total=1, items=[stock(latest_quarter_yoy_pct=-30)])
    monkeypatch.setattr(routes, "get_stocks", load)
    monkeypatch.setattr(routes, "find_latest_aux_file", lambda *args: None)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    body = client.post("/stocks/screen", json={"max_quarter_profit_decline_pct": 50}).json()
    assert body["conditions"]["max_quarter_profit_decline_pct"] == 50
    assert body["items"][0]["status"] == "eligible"
    for value in [0, -10, 101]:
        assert client.post("/stocks/screen", json={"max_quarter_profit_decline_pct": value}).status_code == 422


@pytest.mark.parametrize("quarter", ["latest", "previous"])
@pytest.mark.parametrize("missing", [None, float("nan"), float("inf")])
def test_severe_quarter_wins_nonfinite_peer(quarter, missing):
    peer = "previous" if quarter == "latest" else "latest"
    result = evaluate_stock(stock(**{f"{quarter}_quarter_yoy_pct": -30, f"{peer}_quarter_yoy_pct": missing}), ScreeningRequest())
    assert result.status == "excluded"
    assert any("相邻季度" in reason for reason in result.reasons)
