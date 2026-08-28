"""volume_service 单元测试

mock SSE / SZSE HTTP 响应，验证：
- SSE 总成交额解析（江P callback 格式）
- SZSE 总成交额解析（按"股票"分类汇总）
- 两市合并逻辑（total_amount_yi = sh + sz）
- save_volume_data roundtrip + 与现有 CSV 合并

数据源参考 risk-appetite-skill/scripts/fetch_volume_exchange.py:fetch_sse_volume / fetch_szse_volume。
本项目独立实现，不 import skill。
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.services.data_service import DataService
from src.services.volume_service import VolumeService, _parse_sse_volume, _parse_szse_volume


# ============================================================
# 解析函数单测
# ============================================================

@pytest.mark.unit
def test_parse_sse_volume_extracts_total_amount():
    """解析 SSE JSONP 响应：从 PRODUCT_CODE 01/02/03/11/17 汇总 TRADE_AMT。

    SSE TRADE_AMT 字段单位：亿元（参考 skill fetch_volume_exchange.py:347）。
    """
    sse_json_str = json_str_sample()
    parsed = _parse_sse_volume("2026-08-21", sse_json_str)

    # 预期：所有板块 TRADE_AMT 求和（直接是亿元）
    expected_total = 1000.0 + 50.0 + 800.0 + 100.0 + 500.0  # 01+02+03+11+17 全部计入 total
    assert parsed["status"] == "ok"
    assert parsed["date"] == "2026-08-21"
    assert parsed["total_amount_yi"] == round(expected_total, 2)
    assert parsed["star_board_yi"] == 500.0


@pytest.mark.unit
def test_parse_sse_volume_handles_empty_result():
    """空 result → status=failed"""
    parsed = _parse_sse_volume("2026-08-21", '{"result": null}')
    assert parsed["status"] == "failed"
    assert parsed["total_amount_yi"] is None


@pytest.mark.unit
def test_parse_szse_volume_aggregates_stock_categories():
    """解析 SZSE 响应：'股票'分类汇总 cjje（沪深 A 股 + B 股 + 创业板）"""
    szse_data = [
        {"data": [
            {"lbmc": "主板A股", "cjje": 5000000000.0},   # 主板 A
            {"lbmc": "主板B股", "cjje": 20000000.0},      # 主板 B
            {"lbmc": "创业板", "cjje": 3000000000.0},     # 创业板
            {"lbmc": "基金", "cjje": 99999999999.0},      # 跳过非股票
        ]}
    ]
    parsed = _parse_szse_volume("2026-08-21", szse_data)

    # 期望：5000000000 + 20000000 + 3000000000 = 8020000000 元 = 80200 亿? 不，单位是元，亿=÷1e8 → 80.2 亿
    expected_yi = round((5000000000.0 + 20000000.0 + 3000000000.0) / 1e8, 2)
    assert parsed["status"] == "ok"
    assert parsed["date"] == "2026-08-21"
    assert parsed["total_amount_yi"] == expected_yi
    assert parsed["chinext_yi"] == round(3000000000.0 / 1e8, 2)


@pytest.mark.unit
def test_parse_szse_volume_handles_empty_data():
    """空 data → status=failed"""
    parsed = _parse_szse_volume("2026-08-21", [])
    assert parsed["status"] == "failed"
    assert parsed["total_amount_yi"] is None


# ============================================================
# 两市合并
# ============================================================

@pytest.mark.unit
def test_combine_sse_szse_sums_total_amount_yi():
    """SSE + SZSE 合并：两市 total_amount_yi 相加"""
    svc = VolumeService.__new__(VolumeService)  # 不调用 __init__
    sse_result = {"date": "2026-08-21", "total_amount_yi": 10000.0, "status": "ok"}
    szse_result = {"date": "2026-08-21", "total_amount_yi": 12000.0, "status": "ok"}

    combined = svc._combine(sse_result, szse_result)
    assert combined["total_amount_yi"] == 22000.0
    assert combined["status"] == "ok"
    assert combined["date"] == "2026-08-21"


@pytest.mark.unit
def test_combine_partial_when_one_side_failed():
    """单边失败 → status='partial'，仍返回另一边数据"""
    svc = VolumeService.__new__(VolumeService)
    sse_result = {"date": "2026-08-21", "total_amount_yi": 10000.0, "status": "ok"}
    szse_result = {"date": "2026-08-21", "total_amount_yi": None, "status": "failed"}

    combined = svc._combine(sse_result, szse_result)
    assert combined["total_amount_yi"] == 10000.0
    assert combined["status"] == "partial"


@pytest.mark.unit
def test_combine_failed_when_both_failed():
    """双边失败 → status='failed'"""
    svc = VolumeService.__new__(VolumeService)
    sse_result = {"date": "2026-08-21", "total_amount_yi": None, "status": "failed"}
    szse_result = {"date": "2026-08-21", "total_amount_yi": None, "status": "failed"}

    combined = svc._combine(sse_result, szse_result)
    assert combined["total_amount_yi"] is None
    assert combined["status"] == "failed"


# ============================================================
# save/load roundtrip
# ============================================================

@pytest.mark.integration
def test_save_volume_roundtrip(tmp_path):
    """save_volume_data → load_volume 读回"""
    csv_path = tmp_path / "volume.csv"
    df_to_write = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21"]),
        "total_amount_yi": [12345.67, 13580.12],
    })

    service = DataService()
    service.save_volume_data(df_to_write, path=csv_path)
    assert csv_path.exists()

    loaded = service.load_volume(path=csv_path)
    assert len(loaded) == 2
    assert loaded["total_amount_yi"].iloc[-1] == pytest.approx(13580.12)


@pytest.mark.integration
def test_save_volume_merges_with_existing(tmp_path):
    """save_volume_data 合并现有 CSV（同 date 覆盖）"""
    csv_path = tmp_path / "volume.csv"
    service = DataService()

    first = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21"]),
        "total_amount_yi": [12345.67, 13580.12],
    })
    service.save_volume_data(first, path=csv_path)

    # 第二次：1 条旧日期（覆盖）+ 1 条新日期
    second = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-21", "2026-08-22"]),
        "total_amount_yi": [99999.99, 14000.0],
    })
    service.save_volume_data(second, path=csv_path)

    loaded = service.load_volume(path=csv_path)
    assert len(loaded) == 3
    assert loaded.loc[pd.Timestamp("2026-08-21"), "total_amount_yi"] == pytest.approx(99999.99)
    assert loaded.loc[pd.Timestamp("2026-08-22"), "total_amount_yi"] == pytest.approx(14000.0)


# ============================================================
# helpers
# ============================================================

def json_str_sample() -> str:
    """构造 SSE JSONP 内 JSON 字符串样本"""
    return (
        '{"isPagination":"false","result":['
        '{"PRODUCT_CODE":"01","TRADE_AMT":"1000.00"},'
        '{"PRODUCT_CODE":"02","TRADE_AMT":"50.00"},'
        '{"PRODUCT_CODE":"03","TRADE_AMT":"800.00"},'
        '{"PRODUCT_CODE":"11","TRADE_AMT":"100.00"},'
        '{"PRODUCT_CODE":"17","TRADE_AMT":"500.00"}'
        '],"pageHelp":{"pageSize":10}}'
    )