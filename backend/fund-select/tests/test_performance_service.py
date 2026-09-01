"""
业绩算法单测：给定 mock 净值验证收益 / 回撤（移植算法不动行为）
"""
import pandas as pd

from src.services.performance_service import compute_performance, max_drawdown, period_return

TODAY = pd.Timestamp("2026-09-01")


def _nav(rows: list[tuple[str, float]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["净值日期", "单位净值"])
    df["净值日期"] = pd.to_datetime(df["净值日期"])
    return df.sort_values("净值日期").reset_index(drop=True)


class TestPeriodReturn:
    def test_basic_return(self):
        nav = _nav([("2025-09-01", 1.0), ("2026-08-31", 1.1)])
        r = period_return(nav, 365, today=TODAY)
        assert r == 10.0

    def test_window_too_short_returns_none(self):
        """基准日之前没有净值 → None（如新基金）"""
        nav = _nav([("2026-08-01", 1.0), ("2026-08-31", 1.05)])
        assert period_return(nav, 365, today=TODAY) is None

    def test_empty_nav(self):
        assert period_return(pd.DataFrame(), 365, today=TODAY) is None


class TestMaxDrawdown:
    def test_drawdown_negative(self):
        """1.0 → 1.2 → 0.9：最大回撤 = 0.9/1.2 - 1 = -25%"""
        nav = _nav([("2025-09-01", 1.0), ("2026-03-01", 1.2), ("2026-08-31", 0.9)])
        dd = max_drawdown(nav, 365, today=TODAY)
        assert dd == -25.0

    def test_monotonic_up_zero_drawdown(self):
        nav = _nav([("2025-09-01", 1.0), ("2026-08-31", 1.3)])
        assert max_drawdown(nav, 365, today=TODAY) == 0.0

    def test_window_insufficient(self):
        nav = _nav([("2026-08-31", 1.0)])
        assert max_drawdown(nav, 365, today=TODAY) is None


class TestComputePerformance:
    def test_full_snapshot_keys(self):
        nav = _nav([("2020-09-01", 1.0), ("2025-06-01", 1.4), ("2026-08-31", 1.5)])
        out = compute_performance(nav, today=TODAY)
        assert out["nav_latest"] == 1.5
        assert out["as_of_date"] == TODAY.date()
        assert "ret_1y" in out and "ret_3y" in out and "ret_5y" in out
        assert "dd_3y" in out
        # 窗口基准 = cutoff 前最后一条净值：即使 30 天窗口内只有 1 条，
        # 基准仍是 2025-06-01（cutoff 2026-08-02 之前最后一条）→ ret_1m 有值
        assert out["ret_1m"] == 7.14  # 1.5/1.4 - 1

    def test_returns_none_when_only_recent_nav(self):
        """净值序列全部晚于 cutoff → 该窗口收益缺失"""
        nav = _nav([("2026-08-01", 1.0), ("2026-08-31", 1.05)])
        out = compute_performance(nav, today=TODAY)
        assert "ret_3y" not in out and "ret_1y" not in out

    def test_no_dd_1m_dd_6m_keys(self):
        """库表只存 1y/3y/5y 回撤，不应出现 dd_1m/dd_6m"""
        nav = _nav([("2020-09-01", 1.0), ("2026-08-31", 1.5)])
        out = compute_performance(nav, today=TODAY)
        assert "dd_1m" not in out and "dd_6m" not in out
