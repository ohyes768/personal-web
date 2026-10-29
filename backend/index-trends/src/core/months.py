"""自然月标识工具。

月标识统一为 "YYYY-MM" 字符串（数据层归一，内部不再解析其他格式）。
月份是等间距整数序号，不按自然日/交易日加权——与回归口径一致。
"""
from __future__ import annotations

from datetime import date


def parse_month(month: str) -> tuple[int, int]:
    """解析 "YYYY-MM" 为 (year, month)。非法格式抛 ValueError。"""
    parts = month.split("-")
    if len(parts) != 2:
        raise ValueError(f"非法月标识: {month!r}")
    year, mon = int(parts[0]), int(parts[1])
    if not (1 <= mon <= 12):
        raise ValueError(f"非法月份: {month!r}")
    return year, mon


def format_month(year: int, mon: int) -> str:
    return f"{year:04d}-{mon:02d}"


def month_sequence_index(month: str, origin: str) -> int:
    """month 相对 origin 的整数月序号（origin=0）。month 必须 >= origin。"""
    idx = months_diff(month, origin)
    if idx < 0:
        raise ValueError(f"{month} 早于起点 {origin}")
    return idx


def months_diff(month: str, origin: str) -> int:
    """month - origin 的整月差，可为负。"""
    y1, m1 = parse_month(origin)
    y2, m2 = parse_month(month)
    return (y2 - y1) * 12 + (m2 - m1)


def shift_month(month: str, delta: int) -> str:
    """month 加 delta 个月（delta 可为负）。"""
    y, m = parse_month(month)
    total = y * 12 + (m - 1) + delta
    return format_month(total // 12, total % 12 + 1)


def months_between(start: str, end: str) -> int:
    """end - start 的整月数。"""
    return month_sequence_index(end, start)


def current_month(today: date | None = None) -> str:
    return format_month((today or date.today()).year, (today or date.today()).month)


def is_complete_month(month: str, today: date | None = None) -> bool:
    """未完成自然月不能参加拟合：month 严格早于当前自然月才算完整。"""
    return months_diff(month, current_month(today)) < 0


def check_monthly_continuity(months: list[str], start: str, end: str) -> None:
    """校验 [start, end] 区间内月份连续无缺失。months 必须有序去重。"""
    expected = months_between(start, end) + 1
    if len(months) != expected:
        raise ValueError(f"月份序列不连续: 期望 {expected} 个月, 实际 {len(months)}")
    for i, month in enumerate(months):
        if month != shift_month(start, i):
            raise ValueError(f"月份序列断裂: 位置 {i} 期望 {shift_month(start, i)}, 实际 {month}")
