"""utils/trade_date 单元测试

参考 risk-appetite-skill/scripts/fetch_volume_exchange.py:33-61 get_trade_date() 逻辑。
不 import skill；抄到本项目独立维护。
"""
from datetime import datetime

import pytest

from src.utils.trade_date import get_trade_date


@pytest.mark.unit
def test_weekend_returns_last_friday():
    """周六 → 周五"""
    # 2026-08-22 是周六 → 应返回 2026-08-21（周五）
    sat = datetime(2026, 8, 22, 10, 0, 0)
    assert get_trade_date(sat) == "2026-08-21"


@pytest.mark.unit
def test_sunday_returns_last_friday():
    """周日 → 周五"""
    sun = datetime(2026, 8, 23, 10, 0, 0)
    assert get_trade_date(sun) == "2026-08-21"


@pytest.mark.unit
def test_weekday_during_market_hours_returns_prev_trade_day():
    """交易日盘中(09:30-16:00) → 上一交易日（交易所当日数据未生成）"""
    # 2026-08-24 是周一，10:00 盘中 → 返回 2026-08-21（周五）
    during = datetime(2026, 8, 24, 10, 0, 0)
    assert get_trade_date(during) == "2026-08-21"


@pytest.mark.unit
def test_weekday_after_market_close_returns_today():
    """交易日盘后(>=16:00) → 今日"""
    # 2026-08-24 周一，16:30 → 返回 2026-08-24
    after = datetime(2026, 8, 24, 16, 30, 0)
    assert get_trade_date(after) == "2026-08-24"


@pytest.mark.unit
def test_weekday_before_market_open_returns_today():
    """交易日盘前(<09:30) → 今日（数据已生成于上一交易日盘后，等今日盘后才有）"""
    # 2026-08-24 周一，08:00 → 返回 2026-08-24
    before = datetime(2026, 8, 24, 8, 0, 0)
    assert get_trade_date(before) == "2026-08-24"


@pytest.mark.unit
def test_market_open_boundary_exactly_9_30_returns_prev_day():
    """09:30 边界：盘中起点 → 上一交易日（按 <= 16:00 是盘中区间）"""
    # 2026-08-24 周一，09:30 整 → 视为盘中开始 → 返回 2026-08-21
    boundary = datetime(2026, 8, 24, 9, 30, 0)
    assert get_trade_date(boundary) == "2026-08-21"


@pytest.mark.unit
def test_market_close_boundary_exactly_16_00_returns_today():
    """16:00 边界：盘后起点 → 今日"""
    # 2026-08-24 周一，16:00 整 → 返回 2026-08-24
    boundary = datetime(2026, 8, 24, 16, 0, 0)
    assert get_trade_date(boundary) == "2026-08-24"