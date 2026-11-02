"""自然周标识、周坐标、周序列结构与固定窗口边界。

周标识统一为周一的 "YYYY-MM-DD"（ISO 周一为周首）；week_end 为该周周日。
周坐标 x = (week_start - origin).days / 7 —— 等间距自然周，
整周休市会留下 x 间隔，不能用序号压缩掉时间（regression 层依赖此性质）。

窗口归属一律按 week_end 落入区间判定，避免边界周的归属含糊。

本模块是纯数据结构与纯计算，不依赖数据获取层（src/data）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cached_property

WEEK_LENGTH_DAYS = 7


@dataclass(frozen=True)
class WeeklySample:
    """一个参与拟合的周样本。

    week_start 为周一（自然周主键），trade_date 为该周实际最后交易日。
    坐标 x 由 (week_start - origin).days / 7 得到，整周休市在坐标上留下间隔。
    """

    week_start: str
    trade_date: str
    open: float
    close: float
    high: float
    low: float


@dataclass(frozen=True)
class WeeklyBar:
    """一根周K。week_start 为周一；date 为该周实际最后交易日。"""

    week_start: str
    date: str
    open: float
    close: float
    high: float
    low: float


@dataclass
class WeeklySeries:
    """完整周序列（参与拟合）+ 进行中周（仅展示）+ 休市周（保留时间槽）。

    samples 是参与拟合的完整周样本（唯一事实来源）；complete_weeks / closes
    / bars 是它的派生视图。
    coordinates 是相对 origin 的自然周坐标：整周休市在坐标上留出间隔，
    不得用序号压缩（回归层依赖此性质）。
    """

    samples: list[WeeklySample] = field(default_factory=list)
    partial_bars: dict[str, WeeklyBar] = field(default_factory=dict)
    holiday_weeks: list[str] = field(default_factory=list)
    origin: str | None = None
    coordinates: list[float] = field(default_factory=list)

    @property
    def complete_weeks(self) -> list[str]:
        return [s.week_start for s in self.samples]

    @property
    def closes(self) -> list[float]:
        return [s.close for s in self.samples]

    @cached_property
    def bars(self) -> dict[str, WeeklyBar]:
        """周 K 线视图（按需缓存：逐次重建在千级样本上是 O(n²)）。"""
        return {
            s.week_start: WeeklyBar(
                week_start=s.week_start,
                date=s.trade_date,
                open=s.open,
                close=s.close,
                high=s.high,
                low=s.low,
            )
            for s in self.samples
        }

    @property
    def partial_weeks(self) -> list[str]:
        return sorted(self.partial_bars)

    def week_of(self, week_start: str) -> WeeklyBar | None:
        """取某周 K 线；休市周（无价格）返回 None。"""
        return self.bars.get(week_start)

    def coordinate_of(self, week_start: str) -> float | None:
        """某周的自然周坐标；休市周同样有坐标（保留时间槽）。"""
        if self.origin is None:
            return None
        return week_coordinate_of(week_start, self.origin)


def week_coordinate_of(week_start: str, origin: str) -> float:
    """周相对 origin 的自然周坐标（可为小数间隔）。"""
    return (
        date.fromisoformat(week_start) - date.fromisoformat(origin)
    ).days / WEEK_LENGTH_DAYS


# 近 10 年：10 个日历年的时间跨度（不是 120 周/520 周之类的固定样本数）
TRAILING_WINDOW_YEARS = 10

# 固定历史窗口：名义起点 2005-04-01，每 3 个日历年一个窗口，训练跨度 10 年
FIXED_WINDOW_FIRST_START = date(2005, 4, 1)
FIXED_WINDOW_STEP_YEARS = 3
FIXED_WINDOW_SPAN_YEARS = 10

# 固定窗口观察期：名义区间结束后 3 个日历年（历史观察，不是 156 条有交易周）
FIXED_WINDOW_OBSERVATION_YEARS = 3


def week_start_of(day: date) -> date:
    """返回所在自然周的周一。"""
    return day - timedelta(days=day.weekday())


def week_end_of(week_start: date) -> date:
    """返回该自然周的周日（周一 + 6 天）。"""
    return week_start + timedelta(days=WEEK_LENGTH_DAYS - 1)


def iso_week_label(day: date) -> str:
    """ISO 周标签，如 "2026-W45"。跨年周按 ISO 规则归属（12 月底可能属次年 W01）。"""
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def shift_years(day: date, years: int) -> date:
    """加减日历年；2 月 29 日落到非闰年时取目标年 2 月最后一天。"""
    target_year = day.year + years
    if day.month == 2 and day.day == 29 and not _is_leap(target_year):
        return date(target_year, 2, 28)
    return day.replace(year=target_year)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def week_coordinate(week_start: date, origin: date) -> float:
    """相对 origin 的自然周坐标（可为小数间隔）。"""
    return (week_start - origin).days / WEEK_LENGTH_DAYS


def week_end_in_window(week_start: date, start_inclusive: date, end_exclusive: date) -> bool:
    """周是否归属区间：按该周 week_end（周日）判定 [start, end)。"""
    week_end = week_end_of(week_start)
    return start_inclusive <= week_end < end_exclusive


def trailing_window_bounds(end_exclusive: date) -> tuple[date, date]:
    """近 N 个日历年的窗口区间 [end - N 年, end)。"""
    return shift_years(end_exclusive, -TRAILING_WINDOW_YEARS), end_exclusive


@dataclass(frozen=True)
class FixedWindow:
    """固定历史窗口（名义日历区间，不随数据更新变化）。"""

    index: int
    start_inclusive: date
    end_exclusive: date

    @property
    def stable_id(self) -> str:
        """稳定标识：用名义起点命名，数据更新不变。"""
        return f"fixed-{self.start_inclusive:%Y-%m}"

    @property
    def observation_end_exclusive(self) -> date:
        """观察期上界：名义区间结束后 3 个日历年。"""
        return shift_years(self.end_exclusive, FIXED_WINDOW_OBSERVATION_YEARS)


def fixed_windows(as_of: date) -> list[FixedWindow]:
    """生成截至 as_of 已到达结束边界的全部固定窗口。

    区间结束边界尚未到达时不提前发布完整窗口（不产生未完成的回溯窗口）。
    """
    windows: list[FixedWindow] = []
    start = FIXED_WINDOW_FIRST_START
    index = 1
    while True:
        end = shift_years(start, FIXED_WINDOW_SPAN_YEARS)
        if end > as_of:
            break
        windows.append(FixedWindow(index=index, start_inclusive=start, end_exclusive=end))
        index += 1
        start = shift_years(start, FIXED_WINDOW_STEP_YEARS)
    return windows
