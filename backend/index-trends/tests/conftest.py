"""测试公共设施：脱网 fixture 数据与可注入时间的服务。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.data.provider import KlineBar
from src.data.validate import build_complete_monthly_series
from src.services.store import Store
from src.services.trend_service import SHANGHAI_TZ, TrendService, WeeklyTrendService

FIXTURES = Path(__file__).parent / "fixtures"

# fixture 截止 2026-09；固定"现在"避免真实时间影响完整月判定、投影与收盘判定。
# 取 2026-10-29 18:00（北京时间，盘后）——当日收盘已算完成。
FIXED_NOW = datetime(2026, 10, 29, 18, 0, tzinfo=SHANGHAI_TZ)

# 周K fixture 截止 2026-11-02（进行中周）。固定"现在"= 2026-11-02 18:00：
# 当日 15:05 已过，但本周（11-02 起）尚未结束 → 最近完整周为 2026-10-26 那周。
WEEKLY_FIXED_NOW = datetime(2026, 11, 2, 18, 0, tzinfo=SHANGHAI_TZ)
# 2026-10-30 是当周最后交易日；19:00 周已完成，15:04 尚未完成。
FRIDAY_CLOSE = datetime(2026, 10, 30, 19, 0, tzinfo=SHANGHAI_TZ)
BEFORE_CLOSE = datetime(2026, 10, 30, 15, 4, tzinfo=SHANGHAI_TZ)


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
def weekly_fixture() -> dict:
    """脱网周K fixture（腾讯只读抓取，含进行中的最后一周）。"""
    return json.loads((FIXTURES / "csi300-weekly-2026-11.json").read_text(encoding="utf-8"))


@pytest.fixture()
def weekly_daily_fixture() -> dict:
    return json.loads((FIXTURES / "csi300-daily-2026-11.json").read_text(encoding="utf-8"))


@pytest.fixture()
def weekly_baseline() -> dict:
    """独立数值基准（numpy 最小二乘生成，与 src 实现无关）。"""
    return json.loads((FIXTURES / "csi300-weekly-baseline.json").read_text(encoding="utf-8"))


@pytest.fixture()
def weekly_bars(weekly_fixture: dict) -> list[KlineBar]:
    return [
        KlineBar(
            date=row["date"],
            open=row["open"],
            close=row["close"],
            high=row["high"],
            low=row["low"],
        )
        for row in weekly_fixture["rows"]
    ]


@pytest.fixture()
def weekly_daily_bars(weekly_daily_fixture: dict) -> list[KlineBar]:
    return [
        KlineBar(
            date=row["date"],
            open=row["open"],
            close=row["close"],
            high=row["high"],
            low=row["low"],
        )
        for row in weekly_daily_fixture["rows"]
    ]


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
def weekly_series(weekly_bars) -> "WeeklySeries":
    """用真实周K fixture + SSE 日历构建完整周序列（脱网）。"""
    from src.data.trading_calendar import XshgTradingCalendar
    from src.data.validate import build_weekly_series

    return build_weekly_series(weekly_bars, XshgTradingCalendar(), WEEKLY_FIXED_NOW)


@pytest.fixture()
def now_fn():
    return lambda: FIXED_NOW


@pytest.fixture()
def service(store: Store, now_fn) -> TrendService:
    return TrendService(store, now_fn=now_fn)


@pytest.fixture()
def weekly_published(store: Store, weekly_series, weekly_daily_bars):
    """把脱网周K fixture 发布成一份周线快照（不触网）。"""
    service = WeeklyTrendService(store, now_fn=lambda: FRIDAY_CLOSE)
    models = service.compute_models(weekly_series)
    result = service.publish(weekly_series, weekly_daily_bars, models)
    return service, result


def load_series_into_store(store: Store, series) -> None:
    """把完整月序列与日线注入 store（跳过网络）。"""
    from src.data.validate import to_month_key

    store.upsert_monthly_bars(
        {month: series.bars[month] for month in series.months}
    )
    # 日线：以最后一个完整月月末交易日作为最近已完成交易日
    last = series.bars[series.months[-1]]
    store.upsert_daily_quotes([last])
