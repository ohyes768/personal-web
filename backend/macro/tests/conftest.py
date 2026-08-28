"""宏观信号按月过滤测试夹具

隔离策略:
- macro_signal_data_dir 指向 tmp_path,不触真实 skill 目录
- patch date.today 固定「今天」,让规则推算的 next_release 可精确断言
"""
import json
from datetime import date
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest


TODAY = date(2026, 8, 17)  # 固定今天:8 月中旬,月频指标 8 月份数据尚未发布


class FakeSettings:
    """最小 Settings 替身:macro_signal_service 只用到 macro_signal_data_dir"""

    def __init__(self, data_dir: str):
        self.macro_signal_data_dir = data_dir


def write_skill_json(base: Path, skill: str, file: str, payload: dict) -> None:
    """写一个 skill JSON 到 <base>/<skill>/<file>"""
    target = base / skill / file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_macro_signal(
    data_date: Optional[str],
    conclusion: str = "中性",
    details: Optional[dict] = None,
    generated_at: Optional[str] = None,
) -> dict:
    """构造 macro_signal.json shape"""
    return {
        "dimension": "test",
        "conclusion": conclusion,
        "data_date": data_date,
        "details": details if details is not None else {},
        "generated_at": generated_at,
    }


@pytest.fixture
def skill_dir(tmp_path):
    """空 skill 数据目录(已 patch settings + date.today)"""
    with patch("src.services.macro_signal_service.get_settings", return_value=FakeSettings(str(tmp_path))), \
         patch("src.services.macro_signal_service.date") as mock_date:
        real_date = date  # 保留真实类,静态方法直接用原实现
        mock_date.today.return_value = TODAY
        mock_date.fromisoformat.side_effect = real_date.fromisoformat
        yield tmp_path


@pytest.fixture
def service(skill_dir):
    """全新 MacroSignalService(不带历史缓存)"""
    from src.services.macro_signal_service import MacroSignalService
    return MacroSignalService()
