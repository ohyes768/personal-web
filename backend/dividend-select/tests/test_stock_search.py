"""
股票搜索回归测试（11-11-dividend-all-stock-search）

覆盖 /stocks?search= 的契约：
- 名称包含匹配、代码包含匹配（保留前导零）、大小写、忽略首尾空格
- 搜索覆盖完整收集池：低于股息率阈值的已收集股票也能被搜到
- codes 与搜索取交集（「只看收藏」复用）
- 空关键词保持原行为（阈值筛选仍然生效）
- 搜索不产生任何采集/写盘副作用
"""
import asyncio

import pandas as pd
import pytest
from unittest.mock import Mock

from src.api import routes
from src.services.filter_service import FilterService, normalize_search_keyword


POOL = pd.DataFrame({
    "股票代码": ["000333", "600900", "000651", "600519"],
    "股票名称": ["美的集团", "长江电力", "格力电器", "贵州茅台"],
    "交易所": ["深市主板", "沪市主板", "深市主板", "沪市主板"],
    "3年平均股息率(%)": [2.1, 3.3, 4.5, 2.8],
    "2023年分红(元/股)": [1.0, 0.75, 1.5, 20.0],
    "2024年分红(元/股)": [1.2, 0.85, 2.0, 30.0],
    "2025年分红(元/股)": [1.3, 0.95, 2.2, 35.0],
})


def make_reader(df: pd.DataFrame) -> Mock:
    reader = Mock()
    reader.read_csv.return_value = df
    reader.check_csv_exists.return_value = True
    reader.get_file_mtime.return_value = 1000.0
    reader.get_total_count.return_value = len(df)
    return reader


def patch_routes(monkeypatch, df: pd.DataFrame = POOL) -> pd.DataFrame:
    """真实 FilterService + 真实调用链；只 mock 数据源。"""
    monkeypatch.setattr(routes, "data_reader", make_reader(df))
    monkeypatch.setattr(routes, "filter_service", FilterService())
    sorter = Mock()
    sorter.sort_by_field.side_effect = lambda frame, *a, **k: frame
    monkeypatch.setattr(routes, "sort_service", sorter)
    monkeypatch.setattr(routes, "stock_info_service", None)
    monkeypatch.setattr(routes, "shareholder_reader", None)
    monkeypatch.setattr(routes, "financial_reader", None)
    return df


def call_search(**overrides):
    """走真实路由函数（不 mock get_stocks）。"""
    params = dict(
        min_yield=0, max_yield=None, exchange=None, industry=None,
        index=None, sort_by="avg_yield_3y", sort_order="desc", codes=None,
        search=None,
    )
    params.update(overrides)
    return asyncio.run(routes.get_stocks(**params))


# ---------- 名称 / 代码匹配 ----------

def test_search_matches_name_contains(monkeypatch):
    patch_routes(monkeypatch)
    response = call_search(search="美的")
    assert [item.code for item in response.items] == ["000333"]
    assert response.items[0].name == "美的集团"


def test_search_matches_code_contains_and_keeps_leading_zeros(monkeypatch):
    patch_routes(monkeypatch)
    response = call_search(search="000333")
    assert [item.code for item in response.items] == ["000333"]
    # 前导零不丢：响应里的 code 仍是六位字符串
    assert isinstance(response.items[0].code, str)
    assert response.items[0].code.startswith("000")


def test_search_matches_code_without_leading_zeros(monkeypatch):
    """子串匹配：'00333' 命中 '000333'（代码归一后仍保留前导零语义）。"""
    patch_routes(monkeypatch)
    response = call_search(search="00333")
    assert [item.code for item in response.items] == ["000333"]


def test_search_trims_surrounding_whitespace(monkeypatch):
    patch_routes(monkeypatch)
    response = call_search(search="   美的   ")
    assert [item.code for item in response.items] == ["000333"]


def test_search_is_case_insensitive(monkeypatch):
    df = pd.DataFrame({
        "股票代码": ["600000"],
        "股票名称": ["ABC测试"],
        "交易所": ["沪市主板"],
        "3年平均股息率(%)": [3.0],
    })
    patch_routes(monkeypatch, df)
    response = call_search(search="abc")
    assert [item.code for item in response.items] == ["600000"]


def test_search_no_match_returns_empty(monkeypatch):
    patch_routes(monkeypatch)
    response = call_search(search="未收集公司")
    assert response.total == 0
    assert response.items == []


# ---------- 覆盖完整收集池 ----------

def test_search_ignores_min_yield_threshold(monkeypatch):
    """阈值调到 10%（无股票达标）仍能搜到已收集的低股息率股票。"""
    patch_routes(monkeypatch)
    response = call_search(min_yield=10.0, search="美的")
    assert [item.code for item in response.items] == ["000333"]


def test_search_ignores_exchange_filter(monkeypatch):
    """搜索期间交易所筛选不生效（搜索覆盖完整收集池）。"""
    patch_routes(monkeypatch)
    response = call_search(exchange="沪市主板", search="美的")
    assert [item.code for item in response.items] == ["000333"]


def test_search_empty_keyword_keeps_threshold_behavior(monkeypatch):
    """空/空白关键词 = 未搜索：原阈值筛选仍然生效。"""
    patch_routes(monkeypatch)
    assert call_search(min_yield=3.5, search="").total == 1
    assert call_search(min_yield=3.5, search="   ").total == 1
    assert call_search(min_yield=3.5, search=None).total == 1


def test_search_without_keyword_returns_full_pool(monkeypatch):
    patch_routes(monkeypatch)
    response = call_search(search=None)
    assert response.total == len(POOL)


# ---------- 与 codes 的交集 ----------

def test_search_intersects_with_codes(monkeypatch):
    """codes 与搜索取交集：不在 codes 内的命中项被剔除。"""
    patch_routes(monkeypatch)
    response = call_search(codes="000651,600900", search="长江")
    assert [item.code for item in response.items] == ["600900"]


def test_search_with_codes_leading_zeros(monkeypatch):
    patch_routes(monkeypatch)
    response = call_search(codes="333", search="美的")
    assert [item.code for item in response.items] == ["000333"]


# ---------- 相关度排序 ----------

def test_search_orders_exact_code_first(monkeypatch):
    df = pd.DataFrame({
        "股票代码": ["600333", "000333", "000334"],
        "股票名称": ["同名公司", "同名公司", "另一公司"],
        "交易所": ["沪市主板", "深市主板", "深市主板"],
        "3年平均股息率(%)": [9.9, 1.0, 8.0],
    })
    patch_routes(monkeypatch, df)
    response = call_search(search="000333")
    # 代码全等命中排第一（即使股息率最低）
    assert [item.code for item in response.items][0] == "000333"


def test_search_orders_name_prefix_before_contains(monkeypatch):
    df = pd.DataFrame({
        "股票代码": ["600001", "600002", "600003"],
        "股票名称": ["某某集团", "某某宝", "无关公司"],
        "交易所": ["沪市主板", "沪市主板", "沪市主板"],
        "3年平均股息率(%)": [1.0, 9.0, 8.0],
    })
    patch_routes(monkeypatch, df)
    response = call_search(search="某某")
    # 同为名称前缀命中：按 3 年平均股息率降序（600002 = 9.0 > 600001 = 1.0）
    assert [item.code for item in response.items] == ["600002", "600001"]


# ---------- HTTP 契约 ----------

def test_stocks_http_search_parameter(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    patch_routes(monkeypatch)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    response = client.get("/stocks", params={"search": "美的"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["code"] == "000333"

    # 空白关键词等价于不搜索（min_yield=0 走原筛选链路）
    blank = client.get("/stocks", params={"search": "  ", "min_yield": 0})
    assert blank.status_code == 200
    assert blank.json()["total"] == len(POOL)


def test_screen_route_still_works_with_new_search_param(monkeypatch):
    """内部直接调用 get_stocks 的链路不受新增参数影响（Annotated 写法）。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    patch_routes(monkeypatch)
    monkeypatch.setattr(routes, "find_latest_aux_file", lambda *args: None)
    app = FastAPI()
    app.include_router(routes.router)
    response = TestClient(app).post("/stocks/screen", json={})
    assert response.status_code == 200
    assert response.json()["total"] == len(POOL)


# ---------- 无副作用 ----------

def test_search_does_not_mutate_pool_dataframe(monkeypatch):
    df = patch_routes(monkeypatch)
    before = df.copy()
    call_search(search="美的")
    pd.testing.assert_frame_equal(df, before)


def test_search_does_not_trigger_collection(monkeypatch):
    """搜索只读主 CSV：不触发任何刷新/采集接口。"""
    reader = make_reader(POOL)
    monkeypatch.setattr(routes, "data_reader", reader)
    monkeypatch.setattr(routes, "filter_service", FilterService())
    sorter = Mock()
    sorter.sort_by_field.side_effect = lambda frame, *a, **k: frame
    monkeypatch.setattr(routes, "sort_service", sorter)
    monkeypatch.setattr(routes, "stock_info_service", None)
    monkeypatch.setattr(routes, "shareholder_reader", None)
    monkeypatch.setattr(routes, "financial_reader", None)

    call_search(search="美的")
    reader.read_csv.assert_called_once()
    # 只读了主 CSV，没有写入类调用
    assert not any(
        call for call in reader.mock_calls
        if "write" in call[0] or "save" in call[0] or "refresh" in call[0]
    )


@pytest.mark.parametrize("keyword", ["", "   ", None])
def test_normalize_search_keyword(keyword):
    assert normalize_search_keyword(keyword) == ""
    assert normalize_search_keyword("  美的 ") == "美的"
    assert FilterService.normalize_search_keyword("  美的 ") == "美的"
