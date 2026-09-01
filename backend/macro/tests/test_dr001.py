"""DR001 fetcher 单元测试

数据源:中国货币网 prr-md.json(POST 请求,Referer + X-Requested-With 必带)
响应 data.records[] 中 productCode='DR001' 的 weightedRate 即当日 DR001 加权利率。
"""
import asyncio
import json
from datetime import datetime
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
import requests

from src.services.dr001_service import DR001Service


def _make_payload(product_code: str = "DR001", weighted_rate: str = "1.3576", date_str: str = "26-09-01"):
    """构造与 prr-md.json 真实响应同构的 payload"""
    return {
        "data": {
            "records": [
                {
                    "date": date_str,
                    "productCode": product_code,
                    "latestRate": "1.3223",
                    "weightedRate": weighted_rate,
                    "avgPrd": "1",
                }
            ]
        }
    }


@pytest.mark.unit
def test_extract_dr001_returns_value_and_date():
    """解析:records 中 DR001 的 weightedRate + date 字段正确抽取"""
    payload = _make_payload(weighted_rate="1.3576", date_str="26-09-01")
    out = DR001Service.extract_dr001(payload)
    assert out is not None
    assert out["value"] == pytest.approx(1.3576)
    assert out["data_date"] == "2026-09-01"


@pytest.mark.unit
def test_extract_dr001_skips_other_products_and_picks_dr001():
    """解析:records 含多产品(DR007/DR001/DR014)时只取 DR001"""
    payload = {
        "data": {
            "records": [
                {"date": "26-09-01", "productCode": "DR007", "weightedRate": "1.5000"},
                {"date": "26-09-01", "productCode": "DR001", "weightedRate": "1.3576"},
                {"date": "26-09-01", "productCode": "DR014", "weightedRate": "1.6500"},
            ]
        }
    }
    out = DR001Service.extract_dr001(payload)
    assert out is not None
    assert out["value"] == pytest.approx(1.3576)
    assert out["data_date"] == "2026-09-01"


@pytest.mark.unit
def test_extract_dr001_returns_none_when_missing_record():
    """解析:records 中无 DR001 → None"""
    payload = {
        "data": {
            "records": [
                {"date": "26-09-01", "productCode": "DR007", "weightedRate": "1.5000"},
            ]
        }
    }
    assert DR001Service.extract_dr001(payload) is None


@pytest.mark.unit
def test_extract_dr001_returns_none_when_weighted_rate_missing():
    """解析:DR001 记录存在但 weightedRate 字段缺失 → None"""
    payload = {
        "data": {
            "records": [
                {"date": "26-09-01", "productCode": "DR001", "latestRate": "1.3223"},
            ]
        }
    }
    assert DR001Service.extract_dr001(payload) is None


@pytest.mark.unit
def test_extract_dr001_returns_none_when_weighted_rate_not_float():
    """解析:weightedRate 非数字 → None"""
    payload = {
        "data": {
            "records": [
                {"date": "26-09-01", "productCode": "DR001", "weightedRate": "N/A"},
            ]
        }
    }
    assert DR001Service.extract_dr001(payload) is None


@pytest.mark.unit
def test_extract_dr001_returns_none_for_malformed_payload():
    """解析:响应结构异常 → None(不抛)"""
    assert DR001Service.extract_dr001({}) is None
    assert DR001Service.extract_dr001({"data": "not-dict"}) is None
    assert DR001Service.extract_dr001({"data": {"records": "not-list"}}) is None
    assert DR001Service.extract_dr001(None) is None


@pytest.mark.unit
def test_extract_dr001_returns_none_when_date_missing():
    """解析:weightedRate 存在但 date 字段缺失 → 抽不到合法日期(None)"""
    payload = {
        "data": {
            "records": [
                {"productCode": "DR001", "weightedRate": "1.3576"},
            ]
        }
    }
    out = DR001Service.extract_dr001(payload)
    assert out is not None
    assert out["value"] == pytest.approx(1.3576)
    assert out["data_date"] is None


@pytest.mark.unit
def test_fetch_today_returns_single_row_dataframe():
    """网络:fetch_today 成功 → 单行 DataFrame(index=date, columns=['dr001'])"""
    payload = _make_payload(weighted_rate="1.3576", date_str="26-09-01")

    fake_response = MagicMock()
    fake_response.encoding = "utf-8"
    fake_response.text = json.dumps(payload)

    service = DR001Service()
    with patch.object(service.session, "post", return_value=fake_response):
        df = asyncio.run(service.fetch_today())

    assert list(df.columns) == ["dr001"]
    assert len(df) == 1
    assert df.index[0] == pd.Timestamp("2026-09-01")
    assert df["dr001"].iloc[0] == pytest.approx(1.3576)


@pytest.mark.unit
def test_fetch_today_returns_empty_when_request_fails():
    """网络:session.post 抛错(网络/403/超时) → 空 DataFrame,不抛异常"""
    service = DR001Service()
    with patch.object(
        service.session,
        "post",
        side_effect=requests.exceptions.HTTPError("403 Forbidden"),
    ):
        df = asyncio.run(service.fetch_today())

    assert list(df.columns) == ["dr001"]
    assert len(df) == 0


@pytest.mark.unit
def test_fetch_today_returns_empty_when_field_missing():
    """网络:接口响应中 DR001 缺失 → 空 DataFrame,不抛异常"""
    payload = {
        "data": {
            "records": [
                {"date": "26-09-01", "productCode": "DR007", "weightedRate": "1.5000"},
            ]
        }
    }
    fake_response = MagicMock()
    fake_response.encoding = "utf-8"
    fake_response.text = json.dumps(payload)

    service = DR001Service()
    with patch.object(service.session, "post", return_value=fake_response):
        df = asyncio.run(service.fetch_today())

    assert list(df.columns) == ["dr001"]
    assert len(df) == 0


@pytest.mark.unit
def test_post_uses_referer_and_xrequestedwith_headers():
    """网络:请求必须带 Referer + X-Requested-With 头(否则可能被拒)"""
    payload = _make_payload()
    fake_response = MagicMock()
    fake_response.encoding = "utf-8"
    fake_response.text = json.dumps(payload)

    service = DR001Service()
    with patch.object(service.session, "post", return_value=fake_response) as mock_post:
        asyncio.run(service.fetch_today())

    # 验证 POST 调用时的 headers 包含必带头
    call_kwargs = mock_post.call_args.kwargs
    sent_headers = call_kwargs.get("headers", {})
    # session.headers 会被合并,但 session.headers.update(DEFAULT_HEADERS) 后应包含
    assert "Referer" in service.session.headers
    assert "X-Requested-With" in service.session.headers
    assert service.session.headers["Referer"].startswith("https://www.chinamoney.com.cn")
    assert service.session.headers["X-Requested-With"] == "XMLHttpRequest"
    # POST 而非 GET
    assert mock_post.called
