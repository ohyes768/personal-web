import pathlib

import pytest
from src.api.models import DividendStock, ScreeningRequest
from src.services.screening_service import evaluate_stock, build_checks


def stock(**updates):
    fields = dict(code="000001", name="样本", exchange="深市主板", avg_yield_3y=3.5,
                  dividend_2023=1, dividend_2024=1, dividend_2025=1,
                  roe=10, roe_avg_3y=10, roe_year=2025,
                  roe_history=[dict(year=y, value=10) for y in [2023, 2024, 2025]],
                  net_profit_ex_non_recurring_yoy=0, annual_net_profit_ex_non_recurring=100, annual_profit_year=2025,
                  net_profit_cagr_3y=8,
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
    assert body['conditions']['min_cagr_3y'] == 0
    assert body['items'][0]['stock']['annual_profit_year'] == 2025
    assert body['items'][0]['stock']['annual_net_profit_ex_non_recurring'] == 100
    assert body['total'] == 2
    assert body['financial_last_updated'] == '2026-10-10T01:00:00+08:00'
    assert calls[0] == dict(min_yield=0, max_yield=None, exchange=None, industry=None, index=None, sort_by='avg_yield_3y', sort_order='desc')
    assert TestClient(app).post('/stocks/screen', json={'min_roe': -1}).status_code == 422


def test_cagr_threshold_excludes_shrinking_profit():
    # 默认阈值 0：三年利润缩水即排除
    result = evaluate_stock(stock(net_profit_cagr_3y=-4), ScreeningRequest())
    assert result.status == "excluded"
    assert any("3年复合增长率" in reason for reason in result.reasons)


def test_cagr_threshold_is_inclusive():
    assert evaluate_stock(stock(net_profit_cagr_3y=0), ScreeningRequest()).status == "eligible"
    assert evaluate_stock(stock(net_profit_cagr_3y=-0.01), ScreeningRequest()).status == "excluded"


def test_cagr_threshold_is_configurable():
    request = ScreeningRequest(min_cagr_3y=10)
    assert evaluate_stock(stock(net_profit_cagr_3y=8), request).status == "excluded"
    assert evaluate_stock(stock(net_profit_cagr_3y=12), request).status == "eligible"
    # 负阈值：放宽到"允许三年小幅缩水"
    assert evaluate_stock(stock(net_profit_cagr_3y=-1), ScreeningRequest(min_cagr_3y=-5)).status == "eligible"


def test_uncomputable_cagr_warns_but_does_not_exclude():
    result = evaluate_stock(stock(net_profit_cagr_3y=None), ScreeningRequest())
    assert result.status == "eligible"
    assert any("3年复合增长率不可计算" in warning for warning in result.warnings)


def test_default_cagr_threshold():
    # 默认 0 = 三年利润不缩水（更严的档位由用户在表单里调）
    assert ScreeningRequest().min_cagr_3y == 0


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


# ===== 逐条判定（阅读页「筛选条件复核」） =====


def check_by_key(checks, key):
    return next(check for check in checks if check.key == key)


def test_checks_cover_every_screening_condition():
    checks = build_checks(stock(), ScreeningRequest())
    keys = [check.key for check in checks]
    assert keys == [
        "yield_3y", "dividend_2023", "dividend_2024", "dividend_2025",
        "roe", "roe_avg_3y", "roe_history", "annual_profit", "annual_profit_year",
        "annual_yoy", "cagr_3y", "quarter_decline", "quarter_pair",
    ]
    assert all(check.result == "pass" for check in checks)
    assert check_by_key(checks, "yield_3y").value_text == "3.50%"
    assert check_by_key(checks, "yield_3y").threshold_text == "≥ 3.5%"


def test_checks_mark_threshold_breach_and_missing():
    checks = build_checks(stock(avg_yield_3y=2.0, roe=None), ScreeningRequest())
    assert check_by_key(checks, "yield_3y").result == "fail"
    assert check_by_key(checks, "yield_3y").value_text == "2.00%"
    assert check_by_key(checks, "roe").result == "missing"
    assert check_by_key(checks, "roe").value_text == "待补"


def test_checks_mark_uncomputable_cagr_as_warning_not_failure():
    checks = build_checks(stock(net_profit_cagr_3y=None), ScreeningRequest())
    cagr = check_by_key(checks, "cagr_3y")
    assert cagr.result == "warn"
    assert cagr.value_text == "不可计算"
    assert cagr.reason == ""


def test_checks_mark_single_negative_quarter_as_warning():
    checks = build_checks(stock(latest_quarter_yoy_pct=-10), ScreeningRequest())
    assert check_by_key(checks, "quarter_pair").result == "warn"
    assert check_by_key(checks, "quarter_decline").result == "pass"


def test_checks_keep_reason_order_consistent_with_evaluate_stock():
    samples = [
        stock(),
        stock(avg_yield_3y=1.0, roe=5, roe_avg_3y=2, dividend_2024=0),
        stock(net_profit_ex_non_recurring_yoy=-1, roe_avg_3y=None),
        stock(roe_history=[], roe_year=None, annual_profit_year=None),
        stock(latest_quarter_yoy_pct=-30, previous_quarter_yoy_pct=None),
        stock(previous_quarter_label="2025Q3", previous_quarter_yoy_pct=-50),
        stock(net_profit_cagr_3y=-4, latest_quarter_yoy_pct=-10, previous_quarter_yoy_pct=-5),
    ]
    for sample in samples:
        checks = build_checks(sample, ScreeningRequest())
        item = evaluate_stock(sample, ScreeningRequest())
        failures = [check.reason for check in checks if check.result == "fail" and check.reason]
        missing = [check.reason for check in checks if check.result == "missing" and check.reason]
        warnings = [check.warning for check in checks if check.warning]
        assert item.reasons == failures + missing
        assert item.warnings == warnings


class _StubReader:
    """单股复核接口只需要「数据文件是否存在」与 CSV 路径"""
    csv_path = pathlib.Path("/tmp/does-not-exist.csv")

    def check_csv_exists(self):
        return False


def test_stock_screening_endpoint_returns_checks(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import routes
    monkeypatch.setattr(routes, "data_reader", _StubReader())
    monkeypatch.setattr(routes, "_build_single_stock_model", lambda code: stock(code=code, name="东阿阿胶"))
    monkeypatch.setattr(routes, "find_latest_aux_file", lambda *args: None)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    body = client.get("/stocks/000423/screening").json()
    assert body["code"] == "000423"
    assert body["name"] == "东阿阿胶"
    assert body["status"] == "eligible"
    assert body["conditions"]["min_yield"] == 3.5
    assert body["conditions"]["min_cagr_3y"] == 0
    assert [check["key"] for check in body["checks"]][0] == "yield_3y"
    assert all(check["result"] == "pass" for check in body["checks"])


def test_stock_screening_endpoint_uses_requested_thresholds(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import routes
    monkeypatch.setattr(routes, "data_reader", _StubReader())
    monkeypatch.setattr(routes, "_build_single_stock_model", lambda code: stock(code=code, avg_yield_3y=4.0))
    monkeypatch.setattr(routes, "find_latest_aux_file", lambda *args: None)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    body = client.get("/stocks/000423/screening", params={"min_yield": 5}).json()
    assert body["status"] == "excluded"
    assert any(check["result"] == "fail" and check["key"] == "yield_3y" for check in body["checks"])


@pytest.mark.parametrize("params", [{"min_yield": -1}, {"min_roe": 101}, {"max_quarter_profit_decline_pct": 0},
                                    {"max_quarter_profit_decline_pct": 101}, {"min_cagr_3y": -101}])
def test_stock_screening_endpoint_validates_thresholds(params):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import routes
    app = FastAPI()
    app.include_router(routes.router)
    assert TestClient(app).get("/stocks/000423/screening", params=params).status_code == 422


def test_stock_screening_endpoint_unknown_code(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import routes
    monkeypatch.setattr(routes, "data_reader", _StubReader())
    monkeypatch.setattr(routes, "_build_single_stock_model", lambda code: None)
    app = FastAPI()
    app.include_router(routes.router)
    assert TestClient(app).get("/stocks/999999/screening").status_code == 404


def test_screening_statuses_endpoint_returns_all_codes(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import routes
    from src.api.models import StockListResponse
    monkeypatch.setattr(routes, "data_reader", _StubReader())

    async def load(**kwargs):
        return StockListResponse(total=3, items=[
            stock(code="000001"),
            stock(code="000002", avg_yield_3y=1.0),
            stock(code="000003", latest_quarter_yoy_pct=None),
        ])
    monkeypatch.setattr(routes, "get_stocks", load)
    app = FastAPI()
    app.include_router(routes.router)
    body = TestClient(app).get("/stocks/screen/statuses").json()
    assert body["total"] == 3
    assert body["conditions"]["min_yield"] == 3.5
    statuses = {item["code"]: item["status"] for item in body["items"]}
    assert statuses == {"000001": "eligible", "000002": "excluded", "000003": "insufficient_data"}
    # 只回最小字段，不带股票明细
    assert set(body["items"][0].keys()) == {"code", "status"}


def test_screening_statuses_endpoint_applies_thresholds(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import routes
    from src.api.models import StockListResponse
    monkeypatch.setattr(routes, "data_reader", _StubReader())

    async def load(**kwargs):
        return StockListResponse(total=1, items=[stock(code="000004", avg_yield_3y=4.0)])
    monkeypatch.setattr(routes, "get_stocks", load)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    assert client.get("/stocks/screen/statuses", params={"min_yield": 5}).json()["items"][0]["status"] == "excluded"
    assert client.get("/stocks/screen/statuses", params={"min_yield": 3}).json()["items"][0]["status"] == "eligible"
    assert client.get("/stocks/screen/statuses", params={"min_yield": -1}).status_code == 422
