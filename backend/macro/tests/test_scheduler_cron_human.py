"""cron_to_human 单元测试

覆盖 scheduler.json 两个预设 cron 及常见模式的中文转换。
"""
from __future__ import annotations

import pytest

from src.scheduler.cron_human import cron_to_human


@pytest.mark.unit
@pytest.mark.parametrize(
    "cron,expected",
    [
        # scheduler.json 预设：A 股组 16:30 / 全球组 07:30（工作日）
        ("30 16 * * 1-5", "每周一至周五 16:30"),
        ("30 7 * * 1-5", "每周一至周五 07:30"),
        # 其他常见模式
        ("0 2 * * 6", "每周六 02:00"),
        ("0 2 1 * *", "每月 1 日 02:00"),
        ("0 0 * * *", "每天 00:00"),
        ("*/5 * * * *", "每 5 分钟"),
    ],
)
def test_cron_to_human_common_patterns(cron: str, expected: str):
    assert cron_to_human(cron) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "cron",
    ["garbage", "10 16 * * 1-5 extra", "xx 16 * * 1-5", "10 16 ? * 1-5-x"],
)
def test_cron_to_human_falls_back_to_original(cron: str):
    """无法识别的模式返回原字符串，不抛异常"""
    assert cron_to_human(cron) == cron
