"""周序列校验：完整周判定、缺失周、整周休市、日历越界与日线交叉核对。

关键区分（design.md 第 2 节）：
- 整周休市：日历确认该周无交易日 → 没有周K，不算缺失
- 缺失行情：日历确认该周有交易日但缺条目 / 最后交易日不匹配 → 异常
- 未完成周：可展示，不参与拟合
- 日历越界：calendar_unavailable，不是缺失行情
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.data.provider import KlineBar
from src.data.trading_calendar import CalendarUnavailableError, StaticTradingCalendar
from src.data.validate import (
    MARKET_CLOSE_CUTOFF,
    WeeklyBar,
    build_weekly_series,
    check_weekly_daily_consistency,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _bar(day: str, close: float) -> KlineBar:
    return KlineBar(date=day, open=close, close=close, high=close, low=close)


def _calendar(days: list[str], coverage=(date(2020, 1, 1), date(2030, 12, 31))) -> StaticTradingCalendar:
    return StaticTradingCalendar(
        sessions=[date.fromisoformat(d) for d in days],
        coverage_start=coverage[0],
        coverage_end=coverage[1],
    )


# 2026-11-02 那周：11-02(一) 11-03(二) 11-04(三) 11-05(四) 11-06(五)
WEEK_FULL = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
# 整周休市：2026-11-09 那周无交易日
WEEK_HOLIDAY = "2026-11-09"
# 短周：只有周一一天有交易（其余休市）
WEEK_SHORT = ["2026-11-16"]


def test_week_completes_after_1505_close():
    """周五 15:05 之前该周不算完整，15:05 之后才算。"""
    cal = _calendar(WEEK_FULL)
    bar = _bar("2026-11-06", 100.0)

    before = build_weekly_series([bar], cal, datetime(2026, 11, 6, 15, 4, tzinfo=SHANGHAI))
    assert before.complete_weeks == []
    assert before.partial_weeks == ["2026-11-02"]

    after = build_weekly_series([bar], cal, datetime(2026, 11, 6, 15, 5, tzinfo=SHANGHAI))
    assert after.complete_weeks == ["2026-11-02"]
    assert after.partial_weeks == []


def test_holiday_week_has_no_bar_and_no_error():
    """整周休市：日历确认无交易日 → 没有周K，不是缺失行情。

    供应商在休市周仍返回 K 线（收盘是上一周的重复值），必须丢弃，
    不能当成缺失行情报错，也不能当成真实价格使用。
    """
    cal = _calendar(["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"])
    bars = [_bar("2026-11-06", 110.0), _bar("2026-11-13", 110.0)]  # 后者在休市周
    series = build_weekly_series(bars, cal, datetime(2026, 11, 13, 16, 0, tzinfo=SHANGHAI))
    assert series.complete_weeks == ["2026-11-02"]
    assert series.partial_weeks == []
    assert series.holiday_weeks == ["2026-11-09"]
    assert series.week_of("2026-11-09") is None


def test_missing_week_raises():
    """日历确认有交易日的周整周缺条目 → 缺失行情异常。"""
    cal = _calendar(["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
                     "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13",
                     "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"])
    # 供应商给了 11-02 那周与 11-16 那周，中间 11-09 那周整周缺条目
    bars = [_bar("2026-11-06", 110.0), _bar("2026-11-20", 120.0)]
    with pytest.raises(ValueError) as exc:
        build_weekly_series(bars, cal, datetime(2026, 11, 20, 16, 0, tzinfo=SHANGHAI))
    assert "缺失" in str(exc.value)
    assert "2026-11-09" in str(exc.value)


def test_last_trade_date_mismatch_raises():
    """供应商最后交易日与日历不一致 → 异常（不能默默当成休市）。"""
    cal = _calendar(WEEK_FULL)
    # 供应商说本周最后交易日是 11-03，但日历说 11-06
    bar = _bar("2026-11-03", 100.0)
    with pytest.raises(ValueError) as exc:
        build_weekly_series([bar], cal, datetime(2026, 11, 6, 16, 0, tzinfo=SHANGHAI))
    assert "交易日" in str(exc.value)


def test_calendar_out_of_range_is_not_missing_data():
    """日历越界是 calendar_unavailable，不能混同为缺失行情。"""
    cal = _calendar(WEEK_FULL, coverage=(date(2026, 11, 1), date(2026, 11, 3)))
    bar = _bar("2026-11-02", 100.0)
    with pytest.raises(CalendarUnavailableError):
        build_weekly_series([bar], cal, datetime(2026, 11, 6, 16, 0, tzinfo=SHANGHAI))


def test_future_week_excluded():
    """未完成周（含进行中的本周）不进入完整序列，也不参与拟合。"""
    cal = _calendar(WEEK_FULL)
    bars = [_bar("2026-11-06", 101.0)]
    series = build_weekly_series(bars, cal, datetime(2026, 11, 2, 16, 0, tzinfo=SHANGHAI))
    assert series.complete_weeks == []
    assert series.partial_weeks == ["2026-11-02"]


def test_short_week_completes_on_its_last_session():
    """短周（只有周一有交易）在周一 15:05 后即完成。"""
    cal = _calendar(WEEK_SHORT)
    bar = _bar("2026-11-16", 100.0)
    series = build_weekly_series([bar], cal, datetime(2026, 11, 16, 15, 5, tzinfo=SHANGHAI))
    assert series.complete_weeks == ["2026-11-16"]


def test_holiday_week_keeps_time_slot_without_price():
    """整周休市保留时间槽但无价格：坐标上留间隔，不虚构 K 线。"""
    cal = _calendar(["2026-11-02", "2026-11-03", "2026-11-16"])
    bars = [_bar("2026-11-03", 100.0), _bar("2026-11-16", 110.0)]
    series = build_weekly_series(bars, cal, datetime(2026, 11, 16, 15, 5, tzinfo=SHANGHAI))
    assert series.complete_weeks == ["2026-11-02", "2026-11-16"]
    # 11-09 那周休市 → 两个相邻样本的周坐标差为 2 而不是 1
    xs = series.coordinates
    assert xs[1] - xs[0] == pytest.approx(2.0)
    assert series.week_of("2026-11-02") is not None
    assert series.week_of("2026-11-09") is None    # 休市周没有周K


def test_duplicate_week_raises():
    cal = _calendar(WEEK_FULL)
    bars = [_bar("2026-11-02", 100.0), _bar("2026-11-02", 101.0)]
    with pytest.raises(ValueError):
        build_weekly_series(bars, cal, datetime(2026, 11, 6, 16, 0, tzinfo=SHANGHAI))


def test_non_positive_price_raises():
    cal = _calendar(WEEK_FULL)
    bars = [_bar("2026-11-02", 0.0)]
    with pytest.raises(ValueError):
        build_weekly_series(bars, cal, datetime(2026, 11, 6, 16, 0, tzinfo=SHANGHAI))


def test_non_finite_price_raises():
    """无穷大价格不能靠 OHLC 不等式蒙混过关。"""
    cal = _calendar(WEEK_FULL)
    bars = [
        KlineBar(
            date="2026-11-06",
            open=float("inf"),
            close=float("inf"),
            high=float("inf"),
            low=1.0,
        )
    ]
    with pytest.raises(ValueError, match="非有限"):
        build_weekly_series(bars, cal, datetime(2026, 11, 6, 16, 0, tzinfo=SHANGHAI))


def test_weekly_daily_close_consistency():
    """周K收盘与当周最后交易日日线须一致（0.01 容差）。"""
    weekly = WeeklyBar(
        week_start="2026-11-02", date="2026-11-06",
        open=3985.0, close=3985.50, high=3990.0, low=3980.0,
    )
    assert check_weekly_daily_consistency(weekly, {"2026-11-06": 3985.50}) is True
    assert check_weekly_daily_consistency(weekly, {"2026-11-06": 3985.505}) is True
    assert check_weekly_daily_consistency(weekly, {"2026-11-06": 3900.0}) is False
    assert check_weekly_daily_consistency(weekly, {}) is False


def test_market_close_cutoff_is_1505():
    assert MARKET_CLOSE_CUTOFF == time(15, 5)


def test_year_spanning_week_is_one_week():
    """跨年周（12-30 那周，含元旦）按自然周归属，不拆成两周。"""
    cal = _calendar(["2024-12-30", "2024-12-31", "2025-01-02", "2025-01-03"])
    bar = _bar("2025-01-03", 100.0)
    series = build_weekly_series([bar], cal, datetime(2025, 1, 3, 16, 0, tzinfo=SHANGHAI))
    assert series.complete_weeks == ["2024-12-30"]
    assert len(series.samples) == 1


def test_real_fixture_drops_holiday_week(weekly_series):
    """真实数据里 2012-01-23 那周整周休市：供应商仍给 K 线，必须丢弃。

    该周的收盘与上一周重复，用作本周价格会造出假数据。
    """
    assert "2012-01-23" in weekly_series.holiday_weeks
    assert weekly_series.week_of("2012-01-23") is None
    assert "2012-01-23" not in weekly_series.complete_weeks
    # 前后相邻的完整周仍在
    assert "2012-01-16" in weekly_series.complete_weeks
    assert "2012-01-30" in weekly_series.complete_weeks
