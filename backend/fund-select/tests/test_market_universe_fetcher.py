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
            ("1", "华夏成长", "混合型"),
            ("000001", "华夏成长混合", "混合型"),
            ("161725", "招商中证白酒", "指数型"),
        ])
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            df = fetch_market_universe()
        assert list(df.columns) == ["code", "name", "market_type"]
        # zfill 后 code 标准化为 6 位；前两条 code 相同 → drop_duplicates 保留首条
        assert df["code"].tolist() == ["000001", "161725"]
        assert df.iloc[0]["name"] == "华夏成长"
        assert df.iloc[0]["market_type"] == "混合型"
        assert df.iloc[1]["market_type"] == "指数型"

    def test_empty_result_returns_empty_dataframe(self):
        with patch(
            "src.data.market_universe_fetcher.ak.fund_name_em",
            return_value=pd.DataFrame(columns=["基金代码", "基金简称", "基金类型"]),
        ):
            df = fetch_market_universe()
        assert df.empty
        assert list(df.columns) == ["code", "name", "market_type"]

    def test_empty_result_none_returns_empty_dataframe(self):
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=None):
            df = fetch_market_universe()
        assert df.empty
        assert list(df.columns) == ["code", "name", "market_type"]

    def test_dedup_by_code_keeps_first(self):
        mock_df = _mock_em_df([
            ("000001", "第一条", "债券型"),
            ("000001", "第二条", "债券型"),
        ])
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            df = fetch_market_universe()
        assert len(df) == 1
        assert df.iloc[0]["name"] == "第一条"

    def test_trims_whitespace(self):
        mock_df = _mock_em_df([
            ("000001", "  华夏成长  ", "  债券型  "),
        ])
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            df = fetch_market_universe()
        assert df.iloc[0]["name"] == "华夏成长"
        assert df.iloc[0]["market_type"] == "债券型"

    def test_akshare_raises_propagates(self):
        with patch(
            "src.data.market_universe_fetcher.ak.fund_name_em",
            side_effect=RuntimeError("network error"),
        ):
            with pytest.raises(RuntimeError, match="network error"):
                fetch_market_universe()

    def test_akshare_column_rename_raises(self):
        """akshare 接口列名变更时应抛 KeyError 异常（让上层知道）"""
        mock_df = pd.DataFrame({"code_zh": ["000001"], "name": ["X"], "type": ["债券型"]})
        with patch("src.data.market_universe_fetcher.ak.fund_name_em", return_value=mock_df):
            with pytest.raises(KeyError):
                fetch_market_universe()
