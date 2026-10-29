"""AC1：固定窗口生成规则（120 月窗口 / 36 月步进 / 样本不足返回空）。"""
from __future__ import annotations

from src.core.months import shift_month
from src.core.windows import WINDOW_MONTHS, generate_fixed_windows


def test_258_months_produce_4_windows(fixture_series):
    windows = generate_fixed_windows(fixture_series.months)
    assert len(windows) == 4
    expected = [
        ("2005-04", "2015-03", "2018-03"),
        ("2008-04", "2018-03", "2021-03"),
        ("2011-04", "2021-03", "2024-03"),
        ("2014-04", "2024-03", "2026-09"),  # 观察区不足 36 个月，按实际可用（30 个月）
    ]
    for window, (start, end, obs_end) in zip(windows, expected):
        assert (window.start_month, window.end_month, window.observation_end_month) == (start, end, obs_end)
        assert window.stable_id == f"fixed-{start}"


def test_insufficient_sample_returns_empty():
    months = [shift_month("2005-04", i) for i in range(WINDOW_MONTHS - 1)]
    assert generate_fixed_windows(months) == []


def test_next_window_not_created_until_complete(fixture_series):
    """下一固定窗口 2017-04—2027-03 在拟合完成前不得出现。"""
    windows = generate_fixed_windows(fixture_series.months)
    starts = [w.start_month for w in windows]
    assert "2017-04" not in starts


def test_dynamic_window_emerges_with_new_data(fixture_series):
    """新增完整数据后按相同规则动态产生后续窗口（截取到 2018-03 验证窗口1观察区结束形态）。"""
    months = [m for m in fixture_series.months if m <= "2018-03"]
    windows = generate_fixed_windows(months)
    assert len(windows) == 2
    assert windows[0].end_month == "2015-03"
    assert windows[1].start_month == "2008-04"
