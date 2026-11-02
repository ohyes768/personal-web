"""周标识、自然周坐标与固定窗口边界。

覆盖：跨年 ISO 周、周五 15:04/15:05 判定所需的周边界、
2 月 29 日的 10 年窗口边界、固定窗口步进与"边界未到不发布"。
"""
from __future__ import annotations

from datetime import date

import pytest

from src.core.weeks import (
    FIXED_WINDOW_FIRST_START,
    FIXED_WINDOW_SPAN_YEARS,
    FIXED_WINDOW_STEP_YEARS,
    TRAILING_WINDOW_YEARS,
    fixed_windows,
    iso_week_label,
    shift_years,
    trailing_window_bounds,
    week_coordinate,
    week_end_of,
    week_end_in_window,
    week_start_of,
)


def test_week_start_is_monday():
    assert week_start_of(date(2026, 11, 2)) == date(2026, 11, 2)      # 周一
    assert week_start_of(date(2026, 11, 8)) == date(2026, 11, 2)      # 周日
    assert week_start_of(date(2026, 11, 3)) == date(2026, 11, 2)


def test_week_end_is_sunday():
    assert week_end_of(date(2026, 11, 2)) == date(2026, 11, 8)


def test_iso_week_label_handles_year_boundary():
    """跨年 ISO 周：2024-12-30 属于 2025-W01，2023-01-01 属于 2022-W52。"""
    assert iso_week_label(date(2024, 12, 30)) == "2025-W01"
    assert iso_week_label(date(2023, 1, 1)) == "2022-W52"
    assert iso_week_label(date(2026, 11, 2)) == "2026-W45"


def test_week_coordinate_keeps_holiday_gap():
    """整周休市在坐标上留出间隔，不能用序号压缩掉时间。"""
    origin = date(2026, 1, 5)
    assert week_coordinate(date(2026, 1, 5), origin) == 0.0
    assert week_coordinate(date(2026, 1, 12), origin) == 1.0
    # 1 月 19 日那周休市：下一有交易的周坐标是 2 而不是 1
    assert week_coordinate(date(2026, 1, 26), origin) == 3.0


def test_shift_years_handles_leap_day():
    assert shift_years(date(2028, 2, 29), -10) == date(2018, 2, 28)
    assert shift_years(date(2028, 2, 29), -4) == date(2024, 2, 29)
    assert shift_years(date(2026, 11, 2), -10) == date(2016, 11, 2)


def test_trailing_window_bounds_is_ten_calendar_years():
    start, end = trailing_window_bounds(date(2026, 11, 2))
    assert end == date(2026, 11, 2)
    assert start == date(2016, 11, 2)
    assert TRAILING_WINDOW_YEARS == 10


def test_week_end_membership_uses_sunday():
    """周归属按 week_end（周日）落入区间判定。"""
    # 上界 2026-11-02 = 最近完整周（10-26 那周）的 week_end+1 天
    # → 10-26 那周在窗口内，11-02 那周（week_end 11-08）已在窗口外
    assert week_end_in_window(date(2026, 10, 26), date(2016, 11, 2), date(2026, 11, 2))
    assert not week_end_in_window(date(2026, 11, 2), date(2016, 11, 2), date(2026, 11, 2))
    assert not week_end_in_window(date(2026, 10, 26), date(2016, 11, 2), date(2026, 11, 1))


def test_fixed_windows_step_and_span():
    windows = fixed_windows(date(2026, 11, 2))
    assert [w.start_inclusive.isoformat() for w in windows] == [
        "2005-04-01",
        "2008-04-01",
        "2011-04-01",
        "2014-04-01",
    ]
    for w in windows:
        assert w.end_exclusive == shift_years(w.start_inclusive, FIXED_WINDOW_SPAN_YEARS)
    assert FIXED_WINDOW_FIRST_START == date(2005, 4, 1)
    assert FIXED_WINDOW_STEP_YEARS == 3


def test_fixed_window_not_published_before_boundary():
    """区间结束边界尚未到达时不提前发布完整窗口。"""
    # 首个窗口名义区间到 2015-04-01 结束；2014 年内尚无任何窗口完成
    assert fixed_windows(date(2014, 12, 31)) == []
    windows = fixed_windows(date(2015, 4, 1))
    assert [w.start_inclusive.isoformat() for w in windows] == ["2005-04-01"]
    assert windows[-1].end_exclusive == date(2015, 4, 1)


def test_fixed_window_stable_id_is_stable_across_data_updates():
    """固定窗口 ID 用名义起点命名，数据更新不变（页面稳定选项）。"""
    a = fixed_windows(date(2026, 11, 2))
    b = fixed_windows(date(2027, 5, 1))
    assert [w.stable_id for w in a] == [w.stable_id for w in b[: len(a)]]
    assert a[0].stable_id == "fixed-2005-04"


def test_fixed_window_observation_end_is_three_years_after_nominal_end():
    windows = fixed_windows(date(2026, 11, 2))
    assert windows[0].observation_end_exclusive == date(2018, 4, 1)
    assert windows[-1].observation_end_exclusive == date(2027, 4, 1)


@pytest.mark.parametrize("bad", ["2026-13", "not-a-week"])
def test_invalid_inputs_rejected(bad):
    with pytest.raises(ValueError):
        week_start_of(date.fromisoformat(bad))
