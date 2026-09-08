"""
全市场基金名单 fetcher 单测（mock akshare，不联网）
"""
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.market_universe_fetcher import fetch_market_universe


def _mock_em_df(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    """构造 akshare 返回的 DataFrame：列名与 fund_name_em 一致。"""
    return pd.DataFrame(rows, columns=["基金代码", "基金简称", "基金类型"])


class TestFetchMarketUniverse:
    def test_normalizes_code_to_six_digits(self):
        mock_df = _mock_em_df([
            ("1", "华夏成长", "混合型-灵活"),
            ("000001", "华夏成长混合", "混合型-灵活"),
            ("161725", "招商中证白酒", "指数型-其他"),
        ])
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            df = fetch_market_universe()
        assert list(df.columns) == ["code", "name", "market_subtype", "market_type"]
        # zfill 后 code 标准化为 6 位；前两条 code 相同 → drop_duplicates 保留首条
        assert df["code"].tolist() == ["000001", "161725"]
        assert df.iloc[0]["name"] == "华夏成长"
        assert df.iloc[0]["market_subtype"] == "混合型-灵活"
        assert df.iloc[0]["market_type"] == "stock"   # 混合型-灵活 → stock
        assert df.iloc[1]["market_type"] == "stock"   # 指数型-其他 → stock

    def test_empty_result_returns_empty_dataframe(self):
        with patch(
            "src.data.market_universe_fetcher.ak.fund_name_em",
            return_value=pd.DataFrame(columns=["基金代码", "基金简称", "基金类型"]),
        ):
            df = fetch_market_universe()
        assert df.empty
        assert list(df.columns) == ["code", "name", "market_subtype", "market_type"]

    def test_empty_result_none_returns_empty_dataframe(self):
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=None):
            df = fetch_market_universe()
        assert df.empty
        assert list(df.columns) == ["code", "name", "market_subtype", "market_type"]

    def test_trims_whitespace(self):
        mock_df = _mock_em_df([
            ("000001", "  华夏成长  ", "  债券型-中短债  "),
        ])
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            df = fetch_market_universe()
        assert df.iloc[0]["name"] == "华夏成长"
        assert df.iloc[0]["market_subtype"] == "债券型-中短债"
        assert df.iloc[0]["market_type"] == "bond"

    def test_dedup_by_code_keeps_first(self):
        mock_df = _mock_em_df([
            ("000001", "第一条", "债券型-中短债"),
            ("000001", "第二条", "债券型-中短债"),
        ])
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            df = fetch_market_universe()
        assert len(df) == 1
        assert df.iloc[0]["name"] == "第一条"

    def test_akshare_raises_propagates(self):
        with patch(
            "src.data.market_universe_fetcher.ak.fund_name_em",
            side_effect=RuntimeError("network error"),
        ):
            with pytest.raises(RuntimeError, match="network error"):
                fetch_market_universe()

    def test_akshare_column_rename_raises(self):
        """akshare 接口列名变更时应抛 KeyError 异常（让上层知道）"""
        mock_df = pd.DataFrame({"code_zh": ["000001"], "name": ["X"], "type": ["债券型-中短债"]})
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            with pytest.raises(KeyError):
                fetch_market_universe()

    def test_unknown_subtype_falls_back_to_other(self):
        """akshare 新增未收录子类时降级为 other，不阻塞入库。"""
        mock_df = _mock_em_df([
            ("000001", "未知子类基金", "新类型-X"),
        ])
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            df = fetch_market_universe()
        assert df.iloc[0]["market_subtype"] == "新类型-X"
        assert df.iloc[0]["market_type"] == "other"

    def test_categorize_explicit_mapping(self):
        """关键子类映射正确（防错归股基的固收、防错归债基的纯股指数）。"""
        cases = [
            ("股票型", "stock"),
            ("债券型-中短债", "bond"),
            ("指数型-固收", "bond"),     # 债指数 → bond（关键防错归）
            ("指数型-海外股票", "stock"),
            ("混合型-平衡", "stock"),
            ("QDII-纯债", "bond"),       # 海外债 → bond
            ("QDII-普通股票", "stock"),
            ("FOF-稳健型", "other"),
            ("货币型-普通货币", "other"),
        ]
        mock_df = _mock_em_df([(f"{i:06d}", "X", s) for i, (s, _) in enumerate(cases)])
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            df = fetch_market_universe()
        for (_, expected_cat), row in zip(cases, df.itertuples(index=False)):
            assert row.market_type == expected_cat, f"{row.market_subtype} 应归 {expected_cat}，实归 {row.market_type}"
