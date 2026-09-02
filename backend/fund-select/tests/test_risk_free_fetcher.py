"""
risk_free_fetcher 单测：mock akshare，验证三级降级与单位换算契约。
"""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.risk_free_fetcher import FALLBACK_CONSTANT, fetch_risk_free_rate


def _bond_df(n: int = 500) -> pd.DataFrame:
    """构造 bond_zh_us_rate 风格返回：百分比数字的国债 2Y"""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({"日期": dates.strftime("%Y-%m-%d"), "中国国债收益率2年": [2.1] * n})


class TestFetchRiskFreeRate:
    def test_primary_source_china_gov_2y(self):
        """主源：国债 2Y 百分比数字 → 年化小数"""
        with patch("src.data.risk_free_fetcher.ak.bond_zh_us_rate", return_value=_bond_df()):
            df = fetch_risk_free_rate(date(2024, 1, 1), date(2025, 12, 31))
        assert list(df.columns) == ["date", "rate"]
        assert len(df) > 400
        assert df["rate"].iloc[0] == pytest.approx(0.021)   # 2.1% → 0.021

    def test_primary_source_failure_falls_to_lpr(self):
        """主源网络失败 → LPR 1Y（月度平铺日频）"""
        lpr = pd.DataFrame({
            "TRADE_DATE": ["2024-01-20", "2024-02-20", "2024-03-20"],
            "LPR1Y": [3.45, 3.45, 3.35],
            "LPR5Y": [3.95, 3.95, 3.85],
            "RATE_1": [4.35, 4.35, 4.35],
            "RATE_2": [4.9, 4.9, 4.9],
        })
        with patch("src.data.risk_free_fetcher.ak.bond_zh_us_rate",
                   side_effect=Exception("网络错误")), \
             patch("src.data.risk_free_fetcher.ak.macro_china_lpr", return_value=lpr):
            df = fetch_risk_free_rate(date(2024, 1, 1), date(2024, 3, 31))
        assert len(df) > 40          # 月度 3 点 → 日频平铺
        assert df["rate"].max() == pytest.approx(0.0345)  # 3.45% → 0.0345
        assert df["rate"].iloc[-1] == pytest.approx(0.0335)

    def test_all_sources_fail_constant(self):
        """两级都失败 → 常量兜底"""
        with patch("src.data.risk_free_fetcher.ak.bond_zh_us_rate",
                   side_effect=Exception("网络错误")), \
             patch("src.data.risk_free_fetcher.ak.macro_china_lpr",
                   side_effect=Exception("网络错误")):
            df = fetch_risk_free_rate(date(2024, 1, 1), date(2024, 12, 31))
        assert len(df) == 366        # 自然日历
        assert (df["rate"] == FALLBACK_CONSTANT).all()

    def test_primary_empty_also_falls_to_lpr(self):
        """主源返回空 → 同样降级 LPR"""
        lpr = pd.DataFrame({
            "TRADE_DATE": ["2024-01-20"], "LPR1Y": [3.45],
            "LPR5Y": [3.95], "RATE_1": [4.35], "RATE_2": [4.9],
        })
        with patch("src.data.risk_free_fetcher.ak.bond_zh_us_rate",
                   return_value=pd.DataFrame()), \
             patch("src.data.risk_free_fetcher.ak.macro_china_lpr", return_value=lpr):
            df = fetch_risk_free_rate(date(2024, 1, 1), date(2024, 6, 30))
        assert not df.empty
        assert df["rate"].iloc[0] == pytest.approx(0.0345)
