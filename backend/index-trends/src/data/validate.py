"""数据校验：日期唯一有序、OHLC 逻辑、完整月判定、连续性。

不填补缺失月份伪造连续序列；校验失败抛异常，由调用方转为可见状态。

周线校验（build_weekly_series）同样在此模块，但依赖交易日历：
周线的"完整"判定要看日历确认的最后交易日 15:05 是否已过，
不能只靠自然周边界。三种状态严格区分：
- 整周休市：日历确认该周无交易日 → 没有周K，不算缺失行情
- 缺失行情：日历确认该周有交易日但缺条目 / 最后交易日不匹配 → 异常
- 未完成周：可展示，不参与拟合
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from src.core.months import check_monthly_continuity, format_month, is_complete_month
from src.core.weeks import (
    WEEK_LENGTH_DAYS,
    WeeklyBar,
    WeeklySample,
    WeeklySeries,
    week_coordinate_of,
    week_end_of,
    week_start_of,
)
from src.data.provider import KlineBar
from src.data.trading_calendar import TradingCalendar

# A 股 15:00 收盘；留 5 分钟行情落地缓冲，之前当天收盘不算完成
MARKET_CLOSE_CUTOFF = time(15, 5)

# 周K收盘与日线收盘的交叉核对容差（显示精度）
CLOSE_TOLERANCE = 0.01


@dataclass(frozen=True)
class MonthlySeries:
    """完整自然月序列（不含未完成月）。"""

    months: list[str]
    closes: list[float]
    bars: dict[str, KlineBar]   # month -> bar


def to_month_key(date_str: str) -> str:
    return format_month(int(date_str[:4]), int(date_str[5:7]))


def check_ohlc(bars: list[KlineBar]) -> None:
    for bar in bars:
        if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
            raise ValueError(f"OHLC 逻辑异常: {bar}")


def check_date_order(dates: list[str]) -> None:
    if len(set(dates)) != len(dates):
        raise ValueError("行情日期存在重复")
    if dates != sorted(dates):
        raise ValueError("行情日期非升序")


def build_complete_monthly_series(
    bars: list[KlineBar],
    today=None,
    inception_month: str = "2005-04",
) -> MonthlySeries:
    """从月K构建完整月序列：丢弃发布前数据与未完成月，校验连续性。"""
    if not bars:
        raise ValueError("月K数据为空")
    check_date_order([b.date for b in bars])
    check_ohlc(bars)

    months: list[str] = []
    closes: list[float] = []
    by_month: dict[str, KlineBar] = {}
    for bar in bars:
        month = to_month_key(bar.date)
        if month < inception_month:
            continue    # 发布前回溯数据不混入拟合
        if not is_complete_month(month, today):
            continue    # 未完成自然月不参加拟合
        if month in by_month:
            raise ValueError(f"月K出现重复月份: {month}")
        by_month[month] = bar
        months.append(month)
        closes.append(bar.close)
    if not months:
        raise ValueError("没有完整月数据")
    check_monthly_continuity(months, months[0], months[-1])
    return MonthlySeries(months=months, closes=closes, bars=by_month)


def latest_completed_daily(bars: list[KlineBar], now: datetime) -> KlineBar | None:
    """最近已完成交易日的日线。

    当天行情在收盘缓冲（15:05 Asia/Shanghai）之后才算完成；盘中价不能
    冒充收盘。不依赖输入顺序。
    """
    today_str = now.date().isoformat()
    after_close = now.time() >= MARKET_CLOSE_CUTOFF
    completed = [
        b for b in bars if b.date < today_str or (after_close and b.date == today_str)
    ]
    if not completed:
        return None
    return max(completed, key=lambda b: b.date)


# ---- 周线序列 ----
# WeeklyBar / WeeklySeries / week_coordinate_of 是纯数据结构，定义在
# src/core/weeks.py（core 不依赖 data 层），此处直接复用。


def _week_session_map(
    calendar: TradingCalendar,
    start: date,
    end: date,
) -> dict[str, list[date]]:
    """一次性取区间内会话，按周归组（避免逐周调用日历）。

    区间越界时日历抛 CalendarUnavailableError——与"缺失行情"严格区分。
    """
    sessions = calendar.sessions(start, end)
    grouped: dict[str, list[date]] = {}
    for session in sessions:
        grouped.setdefault(week_start_of(session).isoformat(), []).append(session)
    return grouped


def build_weekly_series(
    bars: list[KlineBar],
    calendar: TradingCalendar,
    now: datetime,
) -> WeeklySeries:
    """从周K构建完整周序列。

    bars 为供应商周K（date 为该周实际最后交易日）。
    now 为当前时间（带时区），用于完成判定。
    """
    if not bars:
        raise ValueError("周K数据为空")

    by_week: dict[str, WeeklyBar] = {}
    for bar in bars:
        prices = (bar.open, bar.close, bar.high, bar.low)
        if not all(math.isfinite(price) for price in prices):
            raise ValueError(f"周K价格非有限: {bar}")
        if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
            raise ValueError(f"周K OHLC 逻辑异常: {bar}")
        if not all(price > 0 for price in prices):
            raise ValueError(f"周K价格非正: {bar}")
        week_start = week_start_of(date.fromisoformat(bar.date)).isoformat()
        if week_start in by_week:
            raise ValueError(f"周K出现重复周: {week_start}")
        by_week[week_start] = WeeklyBar(
            week_start=week_start,
            date=bar.date,
            open=bar.open,
            close=bar.close,
            high=bar.high,
            low=bar.low,
        )

    weeks = sorted(by_week)
    first_week = date.fromisoformat(weeks[0])
    last_provider_week = date.fromisoformat(weeks[-1])

    # 应有截止周：按日历与当前时间推得，不依赖供应商数据（否则供应商整周
    # 跳过时无法察觉）。
    expected_week = expected_last_complete_week(calendar, now)

    range_end = last_provider_week
    if expected_week is not None and expected_week > range_end:
        range_end = expected_week
    sessions_by_week = _week_session_map(
        calendar, first_week, range_end + timedelta(days=WEEK_LENGTH_DAYS - 1)
    )

    complete: list[WeeklySample] = []
    partial_bars: dict[str, WeeklyBar] = {}
    holiday: list[str] = []

    for week_start in weeks:
        bar = by_week[week_start]
        sessions = sessions_by_week.get(week_start, [])
        if not sessions:
            # 日历确认整周休市：供应商却给了 K 线 —— 那是上一周收盘的重复值，
            # 不是本周价格。丢弃该 K 线，保留时间槽（坐标留间隔）。
            holiday.append(week_start)
            continue
        # 该周全部会话都已收盘 → 完整周；供应商标注必须是该周最后交易日
        all_closed = all(
            datetime.combine(s, MARKET_CLOSE_CUTOFF, tzinfo=now.tzinfo) <= now
            for s in sessions
        )
        if all_closed:
            if bar.date != sessions[-1].isoformat():
                raise ValueError(
                    f"周K最后交易日与日历不一致: {week_start} "
                    f"供应商 {bar.date} 日历 {sessions[-1]}"
                )
            complete.append(
                WeeklySample(
                    week_start=week_start,
                    trade_date=bar.date,
                    open=bar.open,
                    close=bar.close,
                    high=bar.high,
                    low=bar.low,
                )
            )
        else:
            # 该周尚未结束 → 进行中周，可展示但不参与拟合
            partial_bars[week_start] = bar

    if expected_week is not None:
        _check_missing_weeks(sessions_by_week, now, first_week, expected_week, by_week)

    series = WeeklySeries(
        samples=complete,
        partial_bars=partial_bars,
        holiday_weeks=holiday,
    )
    if complete:
        series.origin = complete[0].week_start
        series.coordinates = [
            week_coordinate_of(s.week_start, series.origin) for s in complete
        ]
    return series


def expected_last_complete_week(
    calendar: TradingCalendar,
    now: datetime,
    lookback_days: int = 90,
) -> date | None:
    """按日历与当前时间，最近一个"应当已完成"的自然周。

    该周自身最后交易日的 15:05 已过才算完成——本周即使已有交易日收盘，
    只要本周还有交易日未到，整周就还没结束。
    """
    # 看到本周日，才能知道本周后面还有没有交易日。只查到今天会把
    # 周一只收了一天的情况误判成整周已经结束。
    end = week_end_of(week_start_of(now.date()))
    start = end - timedelta(days=lookback_days)
    sessions = calendar.sessions(start, end)
    grouped: dict[str, list[date]] = {}
    for session in sessions:
        grouped.setdefault(week_start_of(session).isoformat(), []).append(session)
    candidates: list[date] = []
    for week_start, days in grouped.items():
        all_closed = all(
            datetime.combine(s, MARKET_CLOSE_CUTOFF, tzinfo=now.tzinfo) <= now
            for s in days
        )
        if all_closed:
            candidates.append(date.fromisoformat(week_start))
    return max(candidates) if candidates else None


def _check_missing_weeks(
    sessions_by_week: dict[str, list[date]],
    now: datetime,
    first_week: date,
    last_week: date,
    by_week: dict[str, WeeklyBar],
) -> None:
    """校验已过 15:05 的应有交易周都有 K 线。

    遍历日历覆盖到的全部自然周（不只是供应商给了 K 线的周），
    否则供应商整周跳过会漏检。
    日历确认整周休市的周不需要 K 线（不是缺失行情）；
    日历确认有交易日的周缺条目 → 缺失行情异常。
    """
    week = first_week
    while week <= last_week:
        sessions = sessions_by_week.get(week.isoformat())
        if sessions:
            all_closed = all(
                datetime.combine(s, MARKET_CLOSE_CUTOFF, tzinfo=now.tzinfo) <= now
                for s in sessions
            )
            if all_closed and week.isoformat() not in by_week:
                raise ValueError(
                    f"缺失应有交易周: {week.isoformat()}（日历最后交易日 {sessions[-1]}）"
                )
        week = week + timedelta(days=WEEK_LENGTH_DAYS)


def check_weekly_daily_consistency(
    weekly: WeeklyBar,
    daily_closes: dict[str, float],
    tolerance: float = CLOSE_TOLERANCE,
) -> bool:
    """周K收盘与当周最后交易日日线是否一致（0.01 显示精度容差）。"""
    daily = daily_closes.get(weekly.date)
    if daily is None:
        return False
    return abs(daily - weekly.close) <= tolerance


def expected_last_session(
    calendar: TradingCalendar,
    now: datetime,
    lookback_days: int = 30,
) -> date | None:
    """当前时刻最近应已收盘的会话日（用于校验日线覆盖度）。"""
    end = now.date()
    start = end - timedelta(days=lookback_days)
    sessions = calendar.sessions(start, end)
    today = end.isoformat()
    after_close = now.time() >= MARKET_CLOSE_CUTOFF
    eligible = [
        s for s in sessions if s.isoformat() < today or (after_close and s.isoformat() == today)
    ]
    return eligible[-1] if eligible else None
