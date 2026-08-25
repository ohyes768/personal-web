"""turnover_service 单元测试

参考 risk-appetite-skill/scripts/fetch_volume_exchange.py:fetch_sse_turnover / fetch_szse_turnover。
本项目独立实现，不 import skill。

合成公式：
  combined = (sh_amt * sh_rate + sz_amt * sz_rate) / (sh_amt + sz_amt)
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from src.services.data_service import DataService
from src.services.turnover_service import (
    TurnoverService,
    _combine_turnover,
    _parse_sse_turnover,
    _parse_szse_turnover,
)


# ============================================================
# 解析函数单测
# ============================================================

@pytest.mark.unit
def test_parse_sse_turnover_extracts_weighted_rate():
    """解析 SSE JSONP：按 TRADE_AMT 加权 TOTAL_TO_RATE。"""
    sse_json_str = (
        '{"isPagination":"false","result":['
        '{"PRODUCT_CODE":"01","TRADE_AMT":"1000.00","TOTAL_TO_RATE":"0.85"},'
        '{"PRODUCT_CODE":"02","TRADE_AMT":"200.00","TOTAL_TO_RATE":"0.50"},'
        '{"PRODUCT_CODE":"11","TRADE_AMT":"300.00","TOTAL_TO_RATE":"1.20"}'
        ']}'
    )
    parsed = _parse_sse_turnover("2026-08-21", sse_json_str)

    # 加权：(1000*0.85 + 200*0.5 + 300*1.2) / (1000+200+300) = (850 + 100 + 360) / 1500 = 1310/1500
    expected = round(1310.0 / 1500.0, 4)
    assert parsed["status"] == "ok"
    assert parsed["turnover_rate"] == expected
    assert parsed["amount_yi"] == 1500.0


@pytest.mark.unit
def test_parse_sse_turnover_handles_empty_result():
    """空 result → status=failed"""
    parsed = _parse_sse_turnover("2026-08-21", '{"result": null}')
    assert parsed["status"] == "failed"
    assert parsed["turnover_rate"] is None


@pytest.mark.unit
def test_parse_szse_turnover_calculates_from_amount_over_capital():
    """解析 SZSE：turnover_rate = cjje / ltsz * 100（单位 %）。"""
    szse_data = [{"data": [
        {"lbmc": "股票", "cjje": 3000000000.0, "ltsz": 30000000000.0},  # 10%
    ]}]
    parsed = _parse_szse_turnover("2026-08-21", szse_data)

    # 3000000000 / 30000000000 * 100 = 10%
    assert parsed["status"] == "ok"
    assert parsed["turnover_rate"] == pytest.approx(10.0, rel=1e-3)
    assert parsed["amount_yi"] == 30.0  # 3000000000 / 1e8 = 30 亿
    assert parsed["ltsz_yi"] == 300.0


@pytest.mark.unit
def test_parse_szse_turnover_handles_missing_stock_row():
    """没找到"股票"分类 → status=failed"""
    szse_data = [{"data": [
        {"lbmc": "基金", "cjje": 100000.0, "ltsz": 1000000.0},
    ]}]
    parsed = _parse_szse_turnover("2026-08-21", szse_data)
    assert parsed["status"] == "failed"


# ============================================================
# 合成
# ============================================================

@pytest.mark.unit
def test_combine_weighted_turnover():
    """两市场按成交额加权合成"""
    sse = {"turnover_rate": 0.8, "amount_yi": 1000.0, "status": "ok"}
    szse = {"turnover_rate": 1.2, "amount_yi": 500.0, "status": "ok"}

    combined = _combine_turnover("2026-08-21", sse, szse)
    # (1000*0.8 + 500*1.2) / (1000+500) = (800 + 600) / 1500 = 1400/1500 = 0.9333
    assert combined["status"] == "ok"
    assert combined["turnover_rate"] == pytest.approx(0.9333, rel=1e-3)


@pytest.mark.unit
def test_combine_partial_when_one_side_failed():
    """单边失败 → 退化为单值（partial）"""
    sse = {"turnover_rate": 0.8, "amount_yi": 1000.0, "status": "ok"}
    szse = {"turnover_rate": None, "amount_yi": None, "status": "failed"}

    combined = _combine_turnover("2026-08-21", sse, szse)
    assert combined["status"] == "partial"
    assert combined["turnover_rate"] == 0.8


@pytest.mark.unit
def test_combine_failed_when_both_failed():
    """双边失败 → failed"""
    sse = {"turnover_rate": None, "status": "failed"}
    szse = {"turnover_rate": None, "status": "failed"}

    combined = _combine_turnover("2026-08-21", sse, szse)
    assert combined["status"] == "failed"
    assert combined["turnover_rate"] is None


# ============================================================
# save/load roundtrip
# ============================================================

@pytest.mark.integration
def test_save_turnover_roundtrip(tmp_path):
    csv_path = tmp_path / "turnover.csv"
    df_to_write = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21"]),
        "turnover_rate": [0.85, 0.92],
    })

    service = DataService()
    service.save_turnover_data(df_to_write, path=csv_path)

    loaded = service.load_turnover(path=csv_path)
    assert len(loaded) == 2
    assert loaded["turnover_rate"].iloc[-1] == pytest.approx(0.92)


@pytest.mark.integration
def test_save_turnover_merges_existing(tmp_path):
    csv_path = tmp_path / "turnover.csv"
    service = DataService()

    first = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20"]),
        "turnover_rate": [0.85],
    })
    service.save_turnover_data(first, path=csv_path)

    second = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21"]),
        "turnover_rate": [0.99, 0.92],
    })
    service.save_turnover_data(second, path=csv_path)

    loaded = service.load_turnover(path=csv_path)
    assert len(loaded) == 2
    assert loaded.loc[pd.Timestamp("2026-08-20"), "turnover_rate"] == pytest.approx(0.99)