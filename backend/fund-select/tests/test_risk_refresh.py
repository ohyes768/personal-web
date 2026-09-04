"""
risk 口径锁定测试：R_p 必须基于东财「日增长率」（复权口径），非累计净值 pct_change。

为什么：东财累计净值 = 单位净值 + 历史分红简单加总（非复权），历史有分红的基金
用 pct_change 会把分红额摊进分母（Δnav/(nav+C)），整条收益序列被稀释，
fund_risk_metrics 6 项指标失真（09-03-fix-risk-adjusted-nav）。

合成序列：单位净值含一次 5% 分红跳变 + 对应日增长率（分红日为除息调整后收益）。
旧口径实现下这些用例会失败（旧实现走 fetch_nav_accumulated，打桩不生效，
测试内不联网即报错，且指标数值对不上）。全程 mock，不联网。
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.db.models import FundBenchmark, FundRiskMetrics
from src.services.risk_service import _risk_returns, refresh_fund_risks
from tests.conftest import _mk_fund

CODE = "673010"
N_DAYS = 900          # ~3.5 年交易日，保证 3 年窗口 > MIN_SAMPLE_DAYS(250)
DIV_IDX = 450         # 分红除息日落在中段
DIVIDEND = 0.05       # 每份分红 0.05 元
DIV_DAY_TRUE_RET = 0.002  # 分红日除息调整后真实日收益（东财日增长率口径）


def _synthetic_nav() -> tuple[pd.DataFrame, np.ndarray, pd.DatetimeIndex]:
    """单位净值 + 日增长率合成序列。

    nav[i] = nav[i-1] * (1 + g[i]) - 分红（仅除息日），即分红日 nav 跳减 5%；
    日增长率恒为 g*100（东财口径：分红日已调整，不出现跳减）。
    返回 (df, g, dates)。
    """
    rng = np.random.default_rng(7)
    g = rng.normal(0.0002, 0.0008, N_DAYS)
    g[DIV_IDX] = DIV_DAY_TRUE_RET
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=N_DAYS)

    nav = np.empty(N_DAYS)
    nav[0] = 1.0
    for i in range(1, N_DAYS):
        nav[i] = nav[i - 1] * (1.0 + g[i]) - (DIVIDEND if i == DIV_IDX else 0.0)

    df = pd.DataFrame({
        "净值日期": dates,
        "单位净值": nav,
        "日增长率": g * 100.0,  # 百分数 float，与真实源一致（如 0.31 = 0.31%）
    })
    return df, g, dates


def _diluted_returns(df: pd.DataFrame) -> pd.Series:
    """旧口径参照：累计净值 pct_change（无分红加总列时与单位净值 pct_change 等价）。"""
    return df.set_index("净值日期")["单位净值"].astype(float).pct_change().dropna()


def _cum(series: pd.Series) -> float:
    return float(np.prod(1 + series) - 1)


class TestRiskReturnsAdjustedBasis:
    """_risk_returns：日增长率复权口径锁定"""

    def test_returns_match_daily_growth_rate_not_nav_pct_change(self):
        """r_p 与「直接用日增长率/100」一致；与单位净值 pct_change 在分红日严重背离"""
        df, g, dates = _synthetic_nav()
        start = dates[DIV_IDX - 100]

        r_p = _risk_returns(df, start)

        in_window = dates >= start
        expected = pd.Series(g[in_window], index=dates[in_window])
        pd.testing.assert_series_equal(
            r_p, expected, check_exact=False, rtol=1e-12, check_freq=False, check_names=False,
        )

        # 分红日：真复权收益 +0.2%，nav pct_change 却约 -4.8%（被 5% 分红稀释）
        div_date = dates[DIV_IDX]
        diluted = _diluted_returns(df)
        assert r_p[div_date] == pytest.approx(DIV_DAY_TRUE_RET, abs=1e-12)
        assert diluted[div_date] - r_p[div_date] < -0.04

    def test_window_filter_and_dropna(self):
        """净值日期 >= start 切窗；日增长率 NaN 行 dropna（与旧口径 dropna 语义一致）"""
        df, _g, dates = _synthetic_nav()
        df.loc[N_DAYS - 1, "日增长率"] = np.nan
        start = dates[N_DAYS // 2]

        r_p = _risk_returns(df, start)

        assert (r_p.index >= start).all()
        assert not r_p.isna().any()
        assert len(r_p) == N_DAYS - N_DAYS // 2 - 1  # 末行 NaN 被丢弃

    def test_empty_nav_returns_empty_series(self):
        r_p = _risk_returns(pd.DataFrame(), pd.Timestamp("2026-01-01"))
        assert r_p.empty


class TestRefreshFundRisksAdjustedBasis:
    """refresh_fund_risks 全链路：入库指标必须来自复权口径"""

    def test_excess_3y_uses_adjusted_compounding(self, db_session, monkeypatch):
        """excess_3y = 日增长率连乘累计 − 基准连乘累计；旧口径（nav pct_change）显著偏小"""
        df, _g, dates = _synthetic_nav()
        # 与 refresh_fund_risks 内部同款窗口（date.today() - 3 年自然日），期望值才能同窗对齐
        start = pd.Timestamp(date.today()) - pd.Timedelta(days=365 * 3)
        assert dates[DIV_IDX] >= start  # 分红日落在窗口内

        tri = 1000.0 * np.cumprod(1 + np.full(N_DAYS, 0.0001))
        db_session.add(_mk_fund(CODE))
        db_session.add_all([
            FundBenchmark(code=CODE, date=d.date(), tri=float(t), source="fetched")
            for d, t in zip(dates, tri)
        ])
        db_session.commit()

        # 打桩 fetch_nav（旧实现调 fetch_nav_accumulated，打桩不生效 → 测试内报错失败）
        monkeypatch.setattr("src.services.risk_service.fetch_nav", lambda code: df)

        errors = refresh_fund_risks(db_session, [CODE])

        assert errors == []
        row = db_session.get(FundRiskMetrics, CODE)
        assert row is not None

        r_p = _risk_returns(df, start)
        r_b = pd.Series(tri, index=dates).pct_change().dropna()
        joined = pd.concat([r_p.rename("p"), r_b.rename("b")], axis=1, join="inner").dropna()
        expected_excess = _cum(joined["p"]) - _cum(joined["b"])
        assert row.excess_3y == pytest.approx(expected_excess, abs=1e-9)
        assert row.sample_days == len(joined) > 250

        # 旧口径把 5% 分红摊进分母 → 累计收益明显偏小（非浮点误差量级）
        diluted = _diluted_returns(df)
        diluted = diluted[diluted.index >= start]
        diluted_joined = pd.concat(
            [diluted.rename("p"), r_b.rename("b")], axis=1, join="inner"
        ).dropna()
        diluted_excess = _cum(diluted_joined["p"]) - _cum(diluted_joined["b"])
        assert expected_excess - diluted_excess > 0.04
