import pytest
from src.api.models import DividendStock, ScreeningRequest
from src.services.screening_service import evaluate_stock


def stock(**updates):
    fields = dict(code="000001", name="样本", exchange="深市主板", avg_yield_3y=3.5,
                  dividend_2023=1, dividend_2024=1, dividend_2025=1,
                  roe=10, roe_avg_3y=10, roe_year=2025,
                  roe_history=[dict(year=y, value=10) for y in [2023, 2024, 2025]],
                  net_profit_ex_non_recurring_yoy=0,
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
