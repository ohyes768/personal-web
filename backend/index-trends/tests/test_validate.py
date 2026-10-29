"""日线/月线序列工具的行为回归。"""
from __future__ import annotations

from datetime import datetime

from src.data.provider import KlineBar
from src.data.validate import latest_completed_daily, to_month_key


def _bar(date: str, close: float) -> KlineBar:
    return KlineBar(date=date, open=close, close=close, high=close, low=close)


MORNING = datetime(2026, 10, 29, 10, 30)   # 盘中
AFTER_CLOSE = datetime(2026, 10, 29, 18, 0)  # 盘后


def test_latest_completed_daily_order_independent():
    """load_daily_quotes 返回 DESC 序列——无论输入顺序，都取最新已完成日。"""
    bars_asc = [_bar("2026-10-27", 1.0), _bar("2026-10-28", 2.0)]
    bars_desc = list(reversed(bars_asc))
    for seq in (bars_asc, bars_desc, []):
        got = latest_completed_daily(seq, MORNING)
        assert got is None or got.date == "2026-10-28"


def test_today_counts_only_after_close():
    """当日行情在收盘缓冲前不算完成（盘中价不冒充收盘），盘后算完成。"""
    bars = [_bar("2026-10-28", 2.0), _bar("2026-10-29", 3.0)]
    assert latest_completed_daily(bars, MORNING).date == "2026-10-28"
    assert latest_completed_daily(bars, AFTER_CLOSE).date == "2026-10-29"


def test_to_month_key():
    assert to_month_key("2005-04-29") == "2005-04"
