"""周线回归：显式 x 坐标、deviation 前移一周、整周休市的 x 间隔。

与月线算法的差异只在坐标系：月线用等间距整数序号，周线用自然周坐标
x = (week_start - origin).days / 7，整周休市会留下间隔。
用可手算的非等距样本独立验证。
"""
from __future__ import annotations

import pytest

from src.core.regression import (
    ALGORITHM_VERSION,
    WEEK_ALGORITHM_VERSION,
    fit_channel,
    fit_weekly_channel,
)

TOL = dict(rel=1e-9)


def test_weekly_algorithm_version_is_distinct():
    """周线用独立算法版本，不改旧月线算法。"""
    assert ALGORITHM_VERSION == "lrc-ltb-port-v1"
    assert WEEK_ALGORITHM_VERSION == "lrc-ltb-week-v1"


def test_weekly_channel_matches_hand_computed_ols():
    """可手算样本：x = [0, 1, 3]（中间一周休市），y = [10, 12, 18]。

    精确推导（有理数）：
      mean_x = 4/3, mean_y = 40/3, sxx = 14/3, sxy = 38/3
      slope = 19/7, intercept = 68/7
      残差 = -17/7, -22/7, -18/7 → deviation = sqrt(1097/147)
    """
    xs = [0.0, 1.0, 3.0]
    ys = [10.0, 12.0, 18.0]
    coeff = fit_weekly_channel(xs, ys)
    assert coeff.slope == pytest.approx(19 / 7, **TOL)
    assert coeff.intercept == pytest.approx(68 / 7, **TOL)
    assert coeff.deviation == pytest.approx((1097 / 147) ** 0.5, **TOL)


def test_weekly_gap_changes_result_vs_compressed_index():
    """关键差异：休市间隔必须进入 x。用序号压缩会得到不同的系数。"""
    xs = [0.0, 1.0, 3.0]
    ys = [10.0, 12.0, 18.0]
    weekly = fit_weekly_channel(xs, ys)
    compressed = fit_weekly_channel([0.0, 1.0, 2.0], ys)
    assert weekly.slope != pytest.approx(compressed.slope, **TOL)
    assert weekly.intercept != pytest.approx(compressed.intercept, **TOL)


def test_weekly_deviation_shifts_baseline_one_week():
    """deviation 基线前移一个自然周（与月线同构，但位移按周计）。"""
    xs = [0.0, 1.0, 2.0]
    ys = [10.0, 20.0, 30.0]
    coeff = fit_weekly_channel(xs, ys)
    # slope = 10, intercept = 10；前移一周后基线 = 10x + 20，残差恒为 -10
    assert coeff.slope == pytest.approx(10.0, **TOL)
    assert coeff.intercept == pytest.approx(10.0, **TOL)
    assert coeff.deviation == pytest.approx(10.0, **TOL)


def test_weekly_and_monthly_agree_on_equally_spaced_samples():
    """等间距周样本下周线与月线算法同构（同样前移一根 K 线）。"""
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [10.0, 20.0, 30.0, 40.0]
    weekly = fit_weekly_channel(xs, ys)
    monthly = fit_channel(ys)
    assert weekly.slope == pytest.approx(monthly.slope, **TOL)
    assert weekly.intercept == pytest.approx(monthly.intercept, **TOL)
    assert weekly.deviation == pytest.approx(monthly.deviation, **TOL)


def test_weekly_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        fit_weekly_channel([], [])
    with pytest.raises(ValueError):
        fit_weekly_channel([0.0], [float("nan")])
    with pytest.raises(ValueError):
        fit_weekly_channel([0.0, 1.0], [100.0, -1.0])
    with pytest.raises(ValueError):
        fit_weekly_channel([0.0, 1.0], [100.0, 101.0], multiplier=0.0)
    with pytest.raises(ValueError):
        fit_weekly_channel([0.0], [100.0])   # 样本不足，无法拟合


def test_weekly_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        fit_weekly_channel([0.0, 1.0], [100.0])


def test_weekly_x_must_be_strictly_increasing():
    with pytest.raises(ValueError):
        fit_weekly_channel([0.0, 0.0], [100.0, 101.0])
    with pytest.raises(ValueError):
        fit_weekly_channel([1.0, 0.0], [100.0, 101.0])


def test_monthly_entry_unchanged():
    """旧月线入口不受周线改动影响。"""
    coeff = fit_channel([100.0, 101.0, 102.0, 103.0])
    assert coeff.slope == pytest.approx(1.0, **TOL)
    assert coeff.intercept == pytest.approx(100.0, **TOL)
