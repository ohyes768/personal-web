"""交易日判断工具 — 跨 volume/turnover/margin 三个 service 共享

参考 risk-appetite-skill/scripts/fetch_volume_exchange.py:33-61 get_trade_date() 逻辑，
本项目内独立维护，避免跨项目依赖。

规则：
- 周末: 往前找最近周五
- 交易日盘中 (09:30 <= now < 16:00): 上一交易日（交易所当日数据未生成）
- 交易日盘前 (< 09:30) / 盘后 (>= 16:00): 今日

注：本工具仅识别周末，**不识别法定节假日**（如国庆、春节）。节假日的回退由调用方
按接口实际返回处理（HTTP 200 但 result 为空 → 上层 fetcher 视为非交易日跳过）。
"""
from __future__ import annotations

from datetime import datetime, time, timedelta


def get_trade_date(now: datetime | None = None) -> str:
    """根据当前时间返回正确的查询交易日（YYYY-MM-DD）。

    Args:
        now: 基准时间，默认为 datetime.now()。传 None 用真实当前时间。

    Returns:
        YYYY-MM-DD 格式的交易日字符串。
    """
    if now is None:
        now = datetime.now()

    # 周末：往前找最近交易日（周一到周五）
    if now.weekday() >= 5:
        date = now
        while date.weekday() >= 5:
            date -= timedelta(days=1)
        return date.strftime("%Y-%m-%d")

    # 交易日判断
    current_time = now.time()
    if time(9, 30) <= current_time < time(16, 0):
        # 盘中：上一交易日
        date = now - timedelta(days=1)
        while date.weekday() >= 5:
            date -= timedelta(days=1)
        return date.strftime("%Y-%m-%d")

    # 盘前/盘后：今日
    return now.strftime("%Y-%m-%d")