"""
ak.fund_open_fund_rank_em fetcher 单测（mock akshare，不联网）
"""
from datetime import date
from unittest.mock import patch
import pandas as pd

from src.data.market_rank_fetcher import (
    fetch_market_rank_page,
    fetch_market_rank_bulk,
)


def _mock_rank_df(seed: int = 0) -> pd.DataFrame:
    """构造 akshare 返回的 DataFrame：用 seed 生成不同 code 验证 dedup 行为"""
    return pd.DataFrame([
        {
            "序号": 1, "基金代码": f"00582{seed}",
            "基金简称": f"基金A{seed}",
            "日期": date(2026, 9, 7),
            "单位净值": 9.606, "累计净值": 10.0484,
            "日增长率": 4.17, "近1周": -1.34, "近1月": 5.12, "近3月": 19.07,
            "近6月": 74.45, "近1年": 140.48, "近2年": 334.9, "近3年": 283.76,
            "今年来": 95.8, "成立来": 1020.34, "自定义": 141.181, "手续费": "0.15%",
        },
        {
            "序号": 2, "基金代码": f"00000{seed + 1}",
            "基金简称": f"基金B{seed}",
            "日期": date(2026, 9, 7),
            "单位净值": 1.5, "累计净值": 2.5,
            "日增长率": 0.5, "近1周": 1.0, "近1月": 2.0, "近3月": 5.0,
            "近6月": 8.0, "近1年": 15.0, "近2年": 30.0, "近3年": 50.0,
            "今年来": 10.0, "成立来": 200.0, "自定义": 50.0, "手续费": "0.10%",
        },
    ])


class TestFetchMarketRankPage:
    def test_normalizes_columns_and_types(self):
        with patch(
            "src.data.market_rank_fetcher.ak.fund_open_fund_rank_em",
            return_value=_mock_rank_df(0),
        ):
            df = fetch_market_rank_page("股票型")
        assert len(df) == 2
        assert "code" in df.columns
        assert df.iloc[0]["code"] == "005820"
        assert df.iloc[0]["name"] == "基金A0"
        assert df.iloc[0]["nav_latest"] == 9.606
        assert df.iloc[0]["nav_date"] == date(2026, 9, 7)
        assert df.iloc[0]["ret_3y"] == 283.76
        assert df.iloc[0]["ret_ytd"] == 95.8
        assert df.iloc[0]["ret_all"] == 1020.34
        assert df.iloc[0]["ft_code"] == "股票型"
        assert df.iloc[0]["fee_buy"] == "0.15%"

    def test_empty_result(self):
        with patch(
            "src.data.market_rank_fetcher.ak.fund_open_fund_rank_em",
            return_value=pd.DataFrame(),
        ):
            df = fetch_market_rank_page("股票型")
        assert df.empty

    def test_handles_akshare_exception(self):
        with patch(
            "src.data.market_rank_fetcher.ak.fund_open_fund_rank_em",
            side_effect=RuntimeError("network error"),
        ):
            df = fetch_market_rank_page("股票型")
        assert df.empty


class TestFetchMarketRankBulk:
    def test_concatenates_multiple_symbols(self):
        call_log = []
        seed_counter = [0]

        def fake_akshare(symbol):
            call_log.append(symbol)
            seed = seed_counter[0]
            seed_counter[0] += 1
            return _mock_rank_df(seed=seed)

        with patch(
            "src.data.market_rank_fetcher.ak.fund_open_fund_rank_em",
            side_effect=fake_akshare,
        ):
            df = fetch_market_rank_bulk(["股票型", "混合型"], page_delay_s=0)
        assert sorted(call_log) == ["混合型", "股票型"]
        # 2 symbols × 2 rows = 4 unique codes（mock 用不同 seed）
        assert len(df) == 4
        assert "code" in df.columns

    def test_default_symbols(self):
        with patch(
            "src.data.market_rank_fetcher.ak.fund_open_fund_rank_em",
            return_value=_mock_rank_df(0),
        ) as mock_ak:
            df = fetch_market_rank_bulk(page_delay_s=0)
        # 默认拉 5 类
        assert mock_ak.call_count == 5

    def test_dedup_by_code(self):
        """同一只基金在多个 symbol 返回时去重"""
        with patch(
            "src.data.market_rank_fetcher.ak.fund_open_fund_rank_em",
            return_value=_mock_rank_df(0),  # 每次返回同样的 005820 + 000001
        ):
            df = fetch_market_rank_bulk(["股票型", "混合型"], page_delay_s=0)
        # 2 symbols × 2 rows = 4 → dedup by code → 2 unique
        assert len(df) == 2

    def test_empty_when_all_symbols_return_empty(self):
        with patch(
            "src.data.market_rank_fetcher.ak.fund_open_fund_rank_em",
            return_value=pd.DataFrame(),
        ):
            df = fetch_market_rank_bulk(["股票型"], page_delay_s=0)
        assert df.empty
        for col in ("code", "nav_latest", "ret_1y", "ret_3y", "ft_code"):
            assert col in df.columns