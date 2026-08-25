"""margin_service 单元测试

数据源：akshare.macro_china_market_margin_sh() + sz()
参考 risk-appetite-skill/scripts/fetch_margin.py:fetch_margin_ohlc
本项目独立实现，不 import skill。

融资融券数据于 T 日 09:45 左右更新前一交易日（T-1）数据。
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from src.services.data_service import DataService
from src.services.margin_service import (
    MarginService,
    _detect_margin_columns,
    _extract_latest_margin,
)


# ============================================================
# 列名识别
# ============================================================

@pytest.mark.unit
def test_detect_margin_columns_precise_match():
    """精确匹配：'融资余额' / '融券余额' 优先于 '融资融券余额'"""
    cols = ["日期", "融资余额", "融资买入额", "融券余额", "融券卖出额", "融资融券余额"]
    mapping = _detect_margin_columns(cols)
    assert mapping is not None
    assert mapping["date"] == "日期"
    assert mapping["rzye"] == "融资余额"
    assert mapping["rqye"] == "融券余额"
    assert mapping["rzje"] == "融资买入额"


@pytest.mark.unit
def test_detect_margin_columns_substring_fallback():
    """子串匹配 fallback：列名带单位也能识别"""
    cols = ["日期", "融资余额(万元)", "融券余额(万元)"]
    mapping = _detect_margin_columns(cols)
    assert mapping is not None
    assert mapping["rzye"] == "融资余额(万元)"
    assert mapping["rqye"] == "融券余额(万元)"


@pytest.mark.unit
def test_detect_margin_columns_excludes_summary():
    """'融资融券余额'汇总列不应被误识别为'融资余额'"""
    cols = ["日期", "融资融券余额", "融资余额", "融券余额"]
    mapping = _detect_margin_columns(cols)
    assert mapping["rzye"] == "融资余额"  # 不是"融资融券余额"


@pytest.mark.unit
def test_detect_margin_columns_returns_none_when_missing():
    """缺关键列（日期 + 融资余额）→ 返回 None"""
    cols = ["date", "foo", "bar"]
    mapping = _detect_margin_columns(cols)
    assert mapping is None


# ============================================================
# 提取最新一行并合并沪+深
# ============================================================

@pytest.mark.unit
def test_extract_latest_margin_sums_sh_and_sz():
    """_extract_latest_margin：合并沪+深最新一行，单位元→亿元（÷1e8）

    akshare macro_china_market_margin_sh/sz 列单位是**元**（沪市实际 ~1e12 元），
    转换为亿元：÷1e8。
    """
    sh_df = pd.DataFrame({
        "日期": pd.to_datetime(["2026-08-19", "2026-08-20"]),
        "融资余额": [1.0e11, 1.5e11],  # 元
        "融券余额": [5.0e9, 6.0e9],
    })
    sz_df = pd.DataFrame({
        "日期": pd.to_datetime(["2026-08-19", "2026-08-20"]),
        "融资余额": [8.0e10, 1.2e11],
        "融券余额": [3.0e9, 4.0e9],
    })

    latest = _extract_latest_margin(sh_df, sz_df, sh_df.columns.tolist(), sz_df.columns.tolist())

    # 最新行是 8-20
    assert latest["date"] == "2026-08-20"
    # (1.5e11 + 1.2e11) / 1e8 = 2.7e3 = 2700 亿元
    assert latest["rzye"] == pytest.approx(2700.0)
    # (6e9 + 4e9) / 1e8 = 1e2 = 100 亿元
    assert latest["rqye"] == pytest.approx(100.0)


# ============================================================
# save/load roundtrip
# ============================================================

@pytest.mark.integration
def test_save_margin_roundtrip(tmp_path):
    csv_path = tmp_path / "margin.csv"
    df_to_write = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21"]),
        "margin_balance_yi": [17800.23, 17850.45],
    })

    service = DataService()
    service.save_margin_data(df_to_write, path=csv_path)

    loaded = service.load_margin(path=csv_path)
    assert len(loaded) == 2
    assert loaded["margin_balance_yi"].iloc[-1] == pytest.approx(17850.45)


@pytest.mark.integration
def test_save_margin_merges_existing(tmp_path):
    csv_path = tmp_path / "margin.csv"
    service = DataService()

    first = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20"]),
        "margin_balance_yi": [17800.23],
    })
    service.save_margin_data(first, path=csv_path)

    second = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21"]),
        "margin_balance_yi": [99999.99, 17850.45],
    })
    service.save_margin_data(second, path=csv_path)

    loaded = service.load_margin(path=csv_path)
    assert len(loaded) == 2
    assert loaded.loc[pd.Timestamp("2026-08-20"), "margin_balance_yi"] == pytest.approx(99999.99)