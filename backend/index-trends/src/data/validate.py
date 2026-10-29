"""数据校验：日期唯一有序、OHLC 逻辑、完整月判定、连续性。

不填补缺失月份伪造连续序列；校验失败抛异常，由调用方转为可见状态。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from src.core.months import check_monthly_continuity, format_month, is_complete_month
from src.data.provider import KlineBar

# A 股 15:00 收盘；留 5 分钟行情落地缓冲，之前当天收盘不算完成
MARKET_CLOSE_CUTOFF = time(15, 5)


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
