"""交易日历适配层：可注入 sessions(start, end)、覆盖范围与异常区分。

脱网：测试用显式会话集构造日历，不依赖系统当前日期与在线日历。
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.data.trading_calendar import (
    CalendarUnavailableError,
    StaticTradingCalendar,
    XshgTradingCalendar,
)


def _dates(*items: str) -> list[date]:
    return [date.fromisoformat(d) for d in items]


@pytest.fixture()
def static_calendar() -> StaticTradingCalendar:
    return StaticTradingCalendar(
        sessions=_dates(
            "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30",
            "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
        ),
        coverage_start=date(2026, 1, 1),
        coverage_end=date(2026, 12, 31),
    )


def test_sessions_returns_sorted_list(static_calendar):
    got = static_calendar.sessions(date(2026, 10, 26), date(2026, 10, 30))
    assert got == _dates("2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30")


def test_sessions_excludes_holiday_and_weekend(static_calendar):
    got = static_calendar.sessions(date(2026, 10, 31), date(2026, 11, 1))
    assert got == []


def test_out_of_coverage_raises_calendar_unavailable(static_calendar):
    with pytest.raises(CalendarUnavailableError):
        static_calendar.sessions(date(2025, 12, 1), date(2026, 1, 15))
    with pytest.raises(CalendarUnavailableError):
        static_calendar.sessions(date(2026, 12, 1), date(2027, 1, 15))


def test_xshg_calendar_covers_launch_week():
    """SSE 日历覆盖 2005-04（沪深300 发布当月），这是"成立以来"起点的前提。"""
    cal = XshgTradingCalendar()
    sessions = cal.sessions(date(2005, 4, 1), date(2005, 4, 30))
    assert len(sessions) == 21
    assert sessions[0] == date(2005, 4, 1)
    assert cal.coverage_start <= date(2005, 4, 1)


def test_xshg_calendar_known_holidays():
    cal = XshgTradingCalendar()
    # 2026 国庆休市：10-01 至 10-07 全休
    assert cal.sessions(date(2026, 10, 1), date(2026, 10, 7)) == []
    assert date(2026, 10, 8) in cal.sessions(date(2026, 10, 8), date(2026, 10, 8))


def test_xshg_calendar_has_upper_bound():
    """库有年份上界：越界必须报错，不得退回"周一到周五皆交易日"。"""
    cal = XshgTradingCalendar()
    assert cal.coverage_end <= date(2027, 12, 31)
    with pytest.raises(CalendarUnavailableError):
        cal.sessions(cal.coverage_end + timedelta(days=1), cal.coverage_end + timedelta(days=40))
