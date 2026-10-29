"""AC5：区域边界 0/25/75/100、负值、超 100、无效宽度。"""
from __future__ import annotations

import pytest

from src.core.models import (
    REGION_ABOVE,
    REGION_BELOW,
    REGION_LOWER,
    REGION_MIDDLE,
    REGION_UPPER,
    InvalidChannelError,
    classify_region,
    position_pct,
)


def _pct(close: float) -> float:
    # lower=0, upper=100 → width=100，position = close%
    return position_pct(close, upper=100.0, lower=0.0)


@pytest.mark.parametrize(
    "close,expected",
    [
        (-0.01, REGION_BELOW),      # <0 通道下方
        (0.0, REGION_LOWER),        # 0 边界归低位
        (0.01, REGION_LOWER),
        (24.999, REGION_LOWER),
        (25.0, REGION_MIDDLE),      # 25 边界归中部
        (50.0, REGION_MIDDLE),
        (74.999, REGION_MIDDLE),
        (75.0, REGION_UPPER),       # 75 边界归高位
        (100.0, REGION_UPPER),      # 100 边界仍属高位
        (100.01, REGION_ABOVE),     # >100 通道上方
        (-50.0, REGION_BELOW),
        (150.0, REGION_ABOVE),
    ],
)
def test_region_boundaries(close, expected):
    assert classify_region(_pct(close)) == expected


def test_position_not_clamped():
    assert _pct(-20.0) == pytest.approx(-20.0)
    assert _pct(120.0) == pytest.approx(120.0)


def test_invalid_width_raises():
    with pytest.raises(InvalidChannelError):
        position_pct(50.0, upper=10.0, lower=10.0)   # 零宽度
    with pytest.raises(InvalidChannelError):
        position_pct(50.0, upper=5.0, lower=10.0)    # 负宽度
    with pytest.raises(InvalidChannelError):
        position_pct(float("nan"), upper=100.0, lower=0.0)
