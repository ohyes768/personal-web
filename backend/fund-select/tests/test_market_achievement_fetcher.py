"""
market_achievement_fetcher 单测（mock，不联网）
"""
from datetime import date
from unittest.mock import patch
import pandas as pd

from src.data.market_achievement_fetcher import (
    fetch_market_achievement,
)


def _mock_ach_df(code: str) -> pd.DataFrame:
    """ak.fund_individual_achievement_xq 返回的 DataFrame"""
    return pd.DataFrame([
        {"业绩类型": "年度业绩", "周期": "1y",
         "本产品区间收益": 15.5, "本产品最大回撒": -3.2,
         "周期收益同类排名": "100/500"},
        {"业绩类型": "阶段业绩", "周期": "3y",
         "本产品区间收益": 50.0, "本产品最大回撒": -8.0,
         "周期收益同类排名": "120/600"},
    ])


class TestFetchMarketAchievement:
    def test_empty_codes(self):
        assert fetch_market_achievement([]) == {}

    def test_concurrent_fetch_success(self):
        def fake_fetch(code):
            return _mock_ach_df(code)
        with patch(
            "src.data.market_achievement_fetcher.fetch_achievement",
            side_effect=fake_fetch,
        ):
            result = fetch_market_achievement(["000001", "000002"], max_workers=2, delay_s=0)
        assert set(result.keys()) == {"000001", "000002"}
        assert len(result["000001"]) == 2

    def test_skip_failures(self):
        """单只失败不影响其他"""
        def fake_fetch(code):
            if code == "000002":
                raise RuntimeError("network error")
            return _mock_ach_df(code)
        with patch(
            "src.data.market_achievement_fetcher.fetch_achievement",
            side_effect=fake_fetch,
        ):
            result = fetch_market_achievement(["000001", "000002"], delay_s=0)
        assert "000001" in result
        assert "000002" not in result  # 失败被跳过

    def test_skip_empty_results(self):
        """空 DataFrame（基金无数据）也跳过"""
        def fake_fetch(code):
            if code == "000002":
                return pd.DataFrame()
            return _mock_ach_df(code)
        with patch(
            "src.data.market_achievement_fetcher.fetch_achievement",
            side_effect=fake_fetch,
        ):
            result = fetch_market_achievement(["000001", "000002"], delay_s=0)
        assert "000001" in result
        assert "000002" not in result
