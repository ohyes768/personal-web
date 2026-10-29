"""测试公共设施：脱网 fixture 数据与可注入时间的服务。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.data.provider import KlineBar
from src.data.validate import build_complete_monthly_series
from src.services.store import Store
from src.services.trend_service import SHANGHAI_TZ, TrendService

FIXTURES = Path(__file__).parent / "fixtures"

# fixture 截止 2026-09；固定"现在"避免真实时间影响完整月判定、投影与收盘判定。
# 取 2026-10-29 18:00（北京时间，盘后）——当日收盘已算完成。
FIXED_NOW = datetime(2026, 10, 29, 18, 0, tzinfo=SHANGHAI_TZ)


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "test.db")


@pytest.fixture()
def monthly_fixture() -> dict:
    return json.loads((FIXTURES / "csi300-monthly-2026-09.json").read_text(encoding="utf-8"))


@pytest.fixture()
def baseline() -> dict:
    return json.loads((FIXTURES / "csi300-baseline.json").read_text(encoding="utf-8"))


@pytest.fixture()
def fixture_series(monthly_fixture: dict):
    """从固定 fixture 构建完整月序列（258 个完整月，截止 2026-09）。"""
    bars = [
        KlineBar(
            date=row["date"],
            open=row["open"],
            close=row["close"],
            high=row["high"],
            low=row["low"],
        )
        for row in monthly_fixture["rows"]
    ]
    return build_complete_monthly_series(
        bars, today=FIXED_NOW.date(), inception_month="2005-04"
    )


@pytest.fixture()
def now_fn():
    return lambda: FIXED_NOW


@pytest.fixture()
def service(store: Store, now_fn) -> TrendService:
    return TrendService(store, now_fn=now_fn)


def load_series_into_store(store: Store, series) -> None:
    """把完整月序列与日线注入 store（跳过网络）。"""
    from src.data.validate import to_month_key

    store.upsert_monthly_bars(
        {month: series.bars[month] for month in series.months}
    )
    # 日线：以最后一个完整月月末交易日作为最近已完成交易日
    last = series.bars[series.months[-1]]
    store.upsert_daily_quotes([last])
