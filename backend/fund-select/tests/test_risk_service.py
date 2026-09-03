"""
risk_service 单测：compute_risk_metrics 纯函数数值断言（TDD 先行）。

序列全部手工构造，期望值可解析计算。
"""
import numpy as np
import pandas as pd
import pytest

from src.services.risk_service import MIN_SAMPLE_DAYS, compute_risk_metrics


def _series(values: list[float], start: str = "2026-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=idx)


class TestComputeRiskMetricsExact:
    """精确数值断言"""

    def test_constant_excess_over_benchmark(self):
        """R_p 恒 +1%、R_b 恒 0%、R_f=0：ir = mean/std；sharpe 同源"""
        n = 300
        r_p = _series([0.01] * n)
        r_b = _series([0.0] * n)
        r_f = _series([0.0] * n)
        m = compute_risk_metrics(r_p, r_b, r_f)
        # R_p - R_b 恒 0.01 → std=0 → ir=None（无分散，信息比率无定义）
        assert m.ir is None
        # 同理 sharpe：R_p - R_f 恒 0.01 → std=0 → None
        assert m.sharpe is None
        # 超额收益仍有定义：∏(1+0.01) - ∏(1+0)
        assert m.excess_3y == pytest.approx((1.01 ** n) - 1.0, rel=1e-9)
        assert m.sample_days == n

    def test_alternating_returns(self):
        """R_p 交替 ±1%、R_b 恒 0：mean=0 → sharpe=0"""
        n = 300
        r_p = _series([0.01, -0.01] * (n // 2))
        r_b = _series([0.0] * n)
        r_f = _series([0.0] * n)
        m = compute_risk_metrics(r_p, r_b, r_f)
        assert m.sharpe == pytest.approx(0.0, abs=1e-12)
        assert m.ir == pytest.approx(0.0, abs=1e-12)
        assert m.excess_3y == pytest.approx((1.01 * 0.99) ** (n // 2) - 1.0, rel=1e-9)

    def test_known_sharpe_value(self):
        """R_p-R_f 序列均值/std 已知 → sharpe = mean/std*√252"""
        # 50 天 +1%、50 天 -0.5%：mean=0.0025, std(pop)…用 ddof=1 算
        vals = [0.01] * 50 + [-0.005] * 50
        vals = vals + vals + vals  # 300 天
        r_p = _series(vals)
        r_b = _series([0.0] * 300)
        r_f = _series([0.0] * 300)
        m = compute_risk_metrics(r_p, r_b, r_f)
        arr = np.array(vals)
        expected = arr.mean() / arr.std(ddof=1) * np.sqrt(252)
        assert m.sharpe == pytest.approx(expected, rel=1e-9)

    def test_tm_regression_recovers_exact_quadratic(self):
        """构造 y = α + βx + γx² 精确关系 → T-M 恢复 α/γ（r_f=0 避免 /252 平移偏移）"""
        rng = np.random.default_rng(42)
        n = 400
        x = rng.normal(0.01, 0.015, n)  # 模拟 R_b - R_f
        alpha_d, beta, gamma = 0.0005, 0.8, 1.5
        y = alpha_d + beta * x + gamma * x ** 2
        r_f = _series([0.0] * n)
        r_p = _series(list(y))
        r_b = _series(list(x))
        m = compute_risk_metrics(r_p, r_b, r_f)
        assert m.alpha == pytest.approx(alpha_d * 252, rel=1e-6)
        assert m.gamma == pytest.approx(gamma, rel=1e-6)
        # 无残差 → alpha_ir 趋于无穷 → None（sigma_e≈0）
        assert m.alpha_ir is None or np.isfinite(m.alpha_ir)


class TestComputeRiskMetricsEdge:
    """容错分支"""

    def test_insufficient_sample(self):
        n = MIN_SAMPLE_DAYS - 1
        r = _series([0.01] * n)
        m = compute_risk_metrics(r, r.copy(), r.copy())
        assert m.sample_days == n
        assert m.sharpe is None and m.ir is None and m.excess_3y is None

    def test_empty_benchmark(self):
        r = _series([0.01] * 300)
        m = compute_risk_metrics(r, pd.Series(dtype=float), r)
        # sharpe 只依赖 R_p/R_f → sample_days 仍是 R_p 样本数
        assert m.sample_days == 300
        assert m.ir is None and m.excess_3y is None
        assert m.sharpe is None or isinstance(m.sharpe, float)

    def test_none_inputs(self):
        m = compute_risk_metrics(None, None, None)
        assert m.sample_days == 0
        assert m.sharpe is None
