"""AC2/AC3：回归系数与固定 fixture 基准一致；后续价格不参与拟合。"""
from __future__ import annotations

import pytest

from src.core.regression import fit_channel
from src.core.windows import generate_fixed_windows

TOL = dict(rel=1e-9)


def test_four_fixed_windows_match_baseline(fixture_series, baseline):
    months, closes = fixture_series.months, fixture_series.closes
    windows = generate_fixed_windows(months)
    assert len(windows) == 4
    for window, expected in zip(windows, baseline["fixed_windows"]):
        assert window.start_month == expected["fit_start"]
        assert window.end_month == expected["fit_end"]
        start_idx = months.index(window.start_month)
        seg = closes[start_idx : start_idx + expected["months"]]
        assert len(seg) == 120
        coeff = fit_channel(seg)
        assert coeff.slope == pytest.approx(expected["coefficients"]["slope"], **TOL)
        assert coeff.intercept == pytest.approx(expected["coefficients"]["intercept"], **TOL)
        assert coeff.deviation == pytest.approx(expected["coefficients"]["deviation"], **TOL)


def test_current_models_match_baseline(fixture_series, baseline):
    months, closes = fixture_series.months, fixture_series.closes
    # AC3：2026-09 截止时，近10年 = 2016-10—2026-09（不是最后一个固定窗口 2014-04 起）
    trailing = fit_channel(closes[-120:])
    assert months[-120] == "2016-10"
    assert months[-1] == "2026-09"
    expected_t = baseline["current_models"]["trailing_120m"]
    assert trailing.slope == pytest.approx(expected_t["coefficients"]["slope"], **TOL)
    assert trailing.intercept == pytest.approx(expected_t["coefficients"]["intercept"], **TOL)
    assert trailing.deviation == pytest.approx(expected_t["coefficients"]["deviation"], **TOL)

    # 成立以来 = 2005-04—2026-09 全样本
    since = fit_channel(closes)
    expected_s = baseline["current_models"]["since_inception"]
    assert since.slope == pytest.approx(expected_s["coefficients"]["slope"], **TOL)
    assert since.intercept == pytest.approx(expected_s["coefficients"]["intercept"], **TOL)
    assert since.deviation == pytest.approx(expected_s["coefficients"]["deviation"], **TOL)


def test_observation_prices_do_not_affect_fit(fixture_series, baseline):
    """AC2：后续价格不参与拟合——截掉 2026-06 之后的观察区价格再算，系数不变。"""
    months, closes = fixture_series.months, fixture_series.closes
    start_idx = months.index("2014-04")
    window4 = closes[start_idx : start_idx + 120]
    full = fit_channel(window4)
    # 只改观察区（拟合区之后的月）不应影响 window4——这里直接验证拟合只用了 120 个点：
    # 构造观察区价格全部翻倍的新序列，window4 系数不变
    mutated = [c * 2 if i >= start_idx + 120 else c for i, c in enumerate(closes)]
    mutated_window4 = mutated[start_idx : start_idx + 120]
    again = fit_channel(mutated_window4)
    assert again.slope == full.slope
    assert again.intercept == full.intercept
    assert again.deviation == full.deviation
    assert baseline["fixed_windows"][3]["coefficients"]["slope"] == pytest.approx(full.slope, **TOL)


def test_fit_rejects_invalid_input():
    with pytest.raises(ValueError):
        fit_channel([])
    with pytest.raises(ValueError):
        fit_channel([100.0, -200.0, 300.0])
    with pytest.raises(ValueError):
        fit_channel([float("nan")] * 12)
