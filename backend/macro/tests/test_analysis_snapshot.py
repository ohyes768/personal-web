"""宏观 Skill 聚合快照 API 契约测试。"""
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

from src.models import MacroIndicator, MacroSignalGroup, MacroSignalSnapshot


class FakeMacroSignalService:
    def __init__(self) -> None:
        self.snapshots = {
            "2026-08": _monthly_snapshot("2026-08", 7.2),
            "2026-09": _monthly_snapshot("2026-09", 7.5),
        }

    def get_available_months(self):
        return ["2026-09", "2026-08"]

    def get_snapshot(self, month):
        return self.snapshots.get(month)


class FakeDailySnapshotService:
    def get_daily_snapshot(self, date=None):
        return {
            "date": date or "2026-09-21",
            "groups": {
                "monetary_policy": {"indicators": [
                    {"key": "dr007", "value": 1.36, "prev_value": 1.42, "data_date": "2026-09-20"},
                ]},
                "exchange_rate": {"indicators": [
                    {"key": "dollar_index", "value": 100.22, "prev_value": 100.23, "data_date": "2026-09-18"},
                ]},
                "risk_appetite": {"indicators": [
                    {"key": "volume", "value": 20771, "prev_value": 18231, "data_date": "2026-09-18"},
                ]},
            },
        }


def _monthly_snapshot(month: str, m2: float) -> MacroSignalSnapshot:
    return MacroSignalSnapshot(
        month=month,
        generated_at=f"{month}-15T09:00:00+08:00",
        groups={
            "monetary_policy": MacroSignalGroup(
                conclusion="适度宽松", total_score=68,
                indicators=[MacroIndicator(key="lpr_1y", value=3.0, data_date=f"{month}-01")],
            ),
            "money_supply": MacroSignalGroup(
                conclusion="适度扩张", total_score=66,
                indicators=[MacroIndicator(key="m2_yoy", value=m2, data_date=f"{month}-13")],
            ),
            "entity_economy": MacroSignalGroup(
                conclusion="稳健", total_score=52,
                indicators=[MacroIndicator(key="pmi_manufacturing", value=49.8, data_date=f"{month}-30")],
            ),
            "inflation": MacroSignalGroup(
                conclusion="温和", total_score=50,
                indicators=[MacroIndicator(key="cpi_yoy", value=0.8, data_date=f"{month}-09")],
            ),
        },
    )


def test_build_returns_ordered_months_and_seven_cards():
    from src.services.analysis_snapshot_service import AnalysisSnapshotService

    result = AnalysisSnapshotService(
        macro_signal_service=FakeMacroSignalService(),
        daily_snapshot_service=FakeDailySnapshotService(),
    ).build(months=["2026-08", "2026-09"], date="2026-09-21")

    assert [period["month"] for period in result["monthly"]["periods"]] == ["2026-08", "2026-09"]
    assert [card["id"] for card in result["monthly"]["periods"][0]["cards"]] == [
        "monetary_policy", "money_supply", "entity_economy", "inflation",
    ]
    assert [card["id"] for card in result["daily"]["cards"]] == [
        "liquidity", "external_pressure", "market_sentiment",
    ]
    daily_indicator = result["daily"]["cards"][0]["indicators"][0]
    assert daily_indicator["change"] == pytest.approx(-0.06)
    assert daily_indicator["is_asof_fallback"] is True
    assert result["quality"]["asof_fallback_keys"] == ["dr007", "dollar_index", "volume"]


def test_build_defaults_to_latest_month_and_keeps_missing_month():
    from src.services.analysis_snapshot_service import AnalysisSnapshotService

    result = AnalysisSnapshotService(FakeMacroSignalService(), FakeDailySnapshotService()).build(
        months=None, date="2026-09-21"
    )
    assert [period["month"] for period in result["monthly"]["periods"]] == ["2026-09"]

    missing = AnalysisSnapshotService(FakeMacroSignalService(), FakeDailySnapshotService()).build(
        months=["2026-07"], date="2026-09-21"
    )
    assert missing["monthly"]["periods"] == [{"month": "2026-07", "status": "unavailable", "cards": []}]


def test_route_rejects_invalid_analysis_snapshot_parameters():
    from src.api.routes import get_analysis_snapshot

    with pytest.raises(HTTPException) as invalid_month:
        get_analysis_snapshot(months="2026/08")
    assert invalid_month.value.status_code == 400

    with pytest.raises(HTTPException) as non_padded_month:
        get_analysis_snapshot(months="2026-8", date=None)
    assert non_padded_month.value.status_code == 400

    with pytest.raises(HTTPException) as too_many_months:
        get_analysis_snapshot(months=",".join(f"2026-{i:02d}" for i in range(1, 14)))
    assert too_many_months.value.status_code == 400

    with pytest.raises(HTTPException) as invalid_date:
        get_analysis_snapshot(months=None, date="2026/09/21")
    assert invalid_date.value.status_code == 400
