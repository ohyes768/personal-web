"""
achievement_fetcher 单测：mock akshare，验证 fetcher contract。

avoid network：测试不依赖真实 akshare，仅验证 fetcher 的输入/输出契约。
"""
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.achievement_fetcher import fetch_achievement


class TestFetchAchievement:
    def test_returns_dataframe(self):
        """正常返回：DataFrame with 原样 columns"""
        fake_df = pd.DataFrame({
            "业绩类型": ["年度业绩", "年度业绩"],
            "周期": ["成立以来", "2025"],
            "本产品区间收益": [50.84, 6.86],
            "本产品最大回撒": [57.91, 13.96],
            "周期收益同类排名": ["1694/5606", "4406/5118"],
        })
        with patch("src.data.achievement_fetcher.ak.fund_individual_achievement_xq", return_value=fake_df) as mock:
            result = fetch_achievement("005827")
        assert mock.call_args.kwargs == {"symbol": "005827"}
        assert list(result.columns) == ["业绩类型", "周期", "本产品区间收益", "本产品最大回撒", "周期收益同类排名"]
        assert len(result) == 2
        assert result.iloc[0]["周期"] == "成立以来"

    def test_empty_dataframe(self):
        """无数据：返回空 DataFrame，不抛异常"""
        empty_df = pd.DataFrame()
        with patch("src.data.achievement_fetcher.ak.fund_individual_achievement_xq", return_value=empty_df):
            result = fetch_achievement("999999")
        assert result.empty

    def test_propagates_exception(self):
        """网络失败 / 基金不存在：抛异常（与 nav_fetcher 契约一致）"""
        with patch(
            "src.data.achievement_fetcher.ak.fund_individual_achievement_xq",
            side_effect=Exception("akshare 网络错误"),
        ), pytest.raises(Exception, match="akshare 网络错误"):
            fetch_achievement("000001")
