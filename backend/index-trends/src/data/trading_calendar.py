"""交易日历适配层。

职责：把"某天是否交易"这件事交给一个有覆盖范围的交易日历，
并把"日历不可用"与"整周休市"区分开——前者是异常，后者是正常的市场事实。

生产实现用 pandas_market_calendars 的 SSE 日历（覆盖 2005-04 起的沪深300 区间，
与 exchange_calendars 的 XSHG 在重叠区间逐日一致）。测试注入显式会话集，
脱网且不受系统当前日期影响。
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Protocol, Sequence


class CalendarUnavailableError(RuntimeError):
    """请求区间超出日历覆盖范围。

    与"整周休市"不同：整周休市是日历给出的正常结果，日历不可用是数据缺口，
    不能退化成"周一到周五都是交易日"。
    """


class TradingCalendar(Protocol):
    """交易日历契约：可注入的 sessions(start, end)。"""

    @property
    def coverage_start(self) -> date:
        """日历覆盖的起始日（含）。"""

    @property
    def coverage_end(self) -> date:
        """日历覆盖的结束日（含）。"""

    def sessions(self, start: date, end: date) -> list[date]:
        """返回 [start, end] 内的交易日（升序）。区间越界抛 CalendarUnavailableError。"""


class StaticTradingCalendar:
    """显式会话集日历（测试与固定夹具用）。"""

    def __init__(
        self,
        sessions: Iterable[date],
        coverage_start: date | None = None,
        coverage_end: date | None = None,
    ):
        self._sessions: list[date] = sorted(set(sessions))
        if not self._sessions:
            raise ValueError("会话集不能为空")
        self._coverage_start = coverage_start or self._sessions[0]
        self._coverage_end = coverage_end or self._sessions[-1]

    @property
    def coverage_start(self) -> date:
        return self._coverage_start

    @property
    def coverage_end(self) -> date:
        return self._coverage_end

    def sessions(self, start: date, end: date) -> list[date]:
        if start > end:
            raise ValueError(f"区间起点晚于终点: {start} > {end}")
        self._check_coverage(start, end)
        return [d for d in self._sessions if start <= d <= end]

    def _check_coverage(self, start: date, end: date) -> None:
        if start < self.coverage_start or end > self.coverage_end:
            raise CalendarUnavailableError(
                f"请求区间 {start} ~ {end} 超出日历覆盖范围 "
                f"{self.coverage_start} ~ {self.coverage_end}"
            )


class XshgTradingCalendar:
    """SSE（上海证券交易所）日历，基于 pandas_market_calendars。

    该库的节假日数据有年份上界：越过上界会静默按"周一到周五皆交易日"处理，
    因此这里显式声明覆盖范围，越界一律抛 CalendarUnavailableError。
    依赖升级后需要重新核验 coverage_end（见 design.md 第 2 节）。
    """

    def __init__(self, calendar_name: str = "SSE"):
        import pandas_market_calendars as mcal

        self._calendar = mcal.get_calendar(calendar_name)
        self._sessions: list[date] | None = None
        adhoc = self._calendar.adhoc_holidays
        # 覆盖范围 = 库内置节假日表覆盖到的年份（含首尾整年）
        self._coverage_start = date(min(adhoc).year, 1, 1)
        self._coverage_end = date(max(adhoc).year, 12, 31)

    @property
    def coverage_start(self) -> date:
        return self._coverage_start

    @property
    def coverage_end(self) -> date:
        return self._coverage_end

    def sessions(self, start: date, end: date) -> list[date]:
        if start > end:
            raise ValueError(f"区间起点晚于终点: {start} > {end}")
        if start < self.coverage_start or end > self.coverage_end:
            raise CalendarUnavailableError(
                f"请求区间 {start} ~ {end} 超出日历覆盖范围 "
                f"{self.coverage_start} ~ {self.coverage_end}"
            )
        # 从缓存的完整会话表切片：逐区间重算 schedule 在长区间上很慢
        return [s for s in self.all_sessions() if start <= s <= end]

    def all_sessions(self) -> Sequence[date]:
        """覆盖范围内的全部交易日（缓存）。"""
        if self._sessions is None:
            schedule = self._calendar.schedule(
                self.coverage_start.isoformat(), self.coverage_end.isoformat()
            )
            self._sessions = sorted({d.date() for d in schedule.index})
        return self._sessions
