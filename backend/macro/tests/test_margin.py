"""margin_service 单元测试

数据源：akshare.macro_china_market_margin_sh() + sz()
参考 risk-appetite-skill/scripts/fetch_margin.py:fetch_margin_ohlc
本项目独立实现，不 import skill。

融资融券数据于 T 日 09:45 左右更新前一交易日（T-1）数据。
"""
from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import pandas as pd
import pytest

from src.services.data_service import DataService
from src.services.margin_service import (
    MarginService,
    _detect_margin_columns,
    _extract_latest_margin,
    _merge_margin_history,
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
# 历史：按日期 outer join 合计（禁止按行号对齐）
# ============================================================

@pytest.mark.unit
def test_merge_margin_history_outer_join_fills_missing_side_with_zero():
    """沪有 8-19/8-20，深有 8-20/8-21 → 三天都保留，缺侧按 0 再合计。"""
    sh_df = pd.DataFrame({
        "日期": pd.to_datetime(["2026-08-19", "2026-08-20"]),
        "融资余额": [1.0e11, 1.5e11],  # 元
    })
    sz_df = pd.DataFrame({
        "日期": pd.to_datetime(["2026-08-20", "2026-08-21"]),
        "融资余额": [8.0e10, 9.0e10],
    })

    merged = _merge_margin_history(sh_df, sz_df)

    assert list(merged["date"].dt.strftime("%Y-%m-%d")) == [
        "2026-08-19", "2026-08-20", "2026-08-21",
    ]
    # 8-19: 仅沪 1e11/1e8 = 1000
    # 8-20: (1.5e11 + 8e10)/1e8 = 2300
    # 8-21: 仅深 9e10/1e8 = 900
    assert merged["margin_balance_yi"].tolist() == pytest.approx([1000.0, 2300.0, 900.0])


@pytest.mark.unit
def test_merge_margin_history_does_not_align_by_row_index():
    """行数不同时禁止 iloc 对齐：深市少一天，不能把深的第一天加到沪的第一天上。"""
    sh_df = pd.DataFrame({
        "日期": pd.to_datetime(["2026-08-18", "2026-08-19", "2026-08-20"]),
        "融资余额": [1.0e10, 2.0e10, 3.0e10],
    })
    sz_df = pd.DataFrame({
        "日期": pd.to_datetime(["2026-08-19", "2026-08-20"]),
        "融资余额": [4.0e10, 5.0e10],
    })

    merged = _merge_margin_history(sh_df, sz_df)
    by_date = dict(zip(
        merged["date"].dt.strftime("%Y-%m-%d"),
        merged["margin_balance_yi"],
    ))
    # 若按 iloc 把深[0] 加到沪[0]：8-18 会变成 500 而不是 100
    assert by_date["2026-08-18"] == pytest.approx(100.0)
    assert by_date["2026-08-19"] == pytest.approx(600.0)
    assert by_date["2026-08-20"] == pytest.approx(800.0)


@pytest.mark.unit
def test_merge_margin_history_returns_none_when_columns_unreadable():
    sh_df = pd.DataFrame({"foo": [1], "bar": [2]})
    sz_df = pd.DataFrame({"foo": [1], "bar": [2]})
    assert _merge_margin_history(sh_df, sz_df) is None


@pytest.mark.unit
def test_fetch_history_returns_merged_frame():
    sh_df = pd.DataFrame({
        "日期": pd.to_datetime(["2026-08-19", "2026-08-20"]),
        "融资余额": [1.0e11, 1.5e11],
    })
    sz_df = pd.DataFrame({
        "日期": pd.to_datetime(["2026-08-20"]),
        "融资余额": [8.0e10],
    })
    svc = MarginService()
    with patch.object(svc, "_get_akshare") as mock_ak:
        mock_ak.return_value.macro_china_market_margin_sh.return_value = sh_df.copy()
        mock_ak.return_value.macro_china_market_margin_sz.return_value = sz_df.copy()
        result = svc.fetch_history()

    assert result["status"] == "ok"
    df = result["data"]
    assert len(df) == 2
    assert df.loc[df["date"] == pd.Timestamp("2026-08-19"), "margin_balance_yi"].iloc[0] == pytest.approx(1000.0)


@pytest.mark.unit
def test_fetch_history_failed_when_akshare_empty():
    svc = MarginService()
    empty = pd.DataFrame(columns=["日期", "融资余额"])
    with patch.object(svc, "_get_akshare") as mock_ak:
        mock_ak.return_value.macro_china_market_margin_sh.return_value = empty
        mock_ak.return_value.macro_china_market_margin_sz.return_value = empty
        result = svc.fetch_history()

    assert result["status"] == "failed"
    assert result["data"].empty


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