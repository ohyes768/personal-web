"""将月度宏观信号与日频快照投影为外部 Skill 的稳定七卡数据源。"""
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from src.services.daily_snapshot_service import DailySnapshotService
from src.services.macro_signal_service import MacroSignalService


_MONTHLY_CARDS = (
    ("monetary_policy", "货币政策"),
    ("money_supply", "信用扩张"),
    ("entity_economy", "经济运行"),
    ("inflation", "通胀环境"),
)
_DAILY_CARDS = (
    ("liquidity", "流动性", "monetary_policy"),
    ("external_pressure", "外部压力", "exchange_rate"),
    ("market_sentiment", "市场情绪", "risk_appetite"),
)
_INDICATOR_META = {
    "lpr_1y": ("1年期 LPR", "%"), "lpr_5y": ("5年期 LPR", "%"),
    "mlf_net_yi": ("MLF 净投放", "亿"), "m2_yoy": ("M2 同比", "%"),
    "m1_yoy": ("M1 同比", "%"), "social_yoy": ("社融存量同比", "%"),
    "m2_m1_spread": ("M2-M1 剪刀差", "%"), "spread_change_pp": ("剪刀差环比", "pp"),
    "pmi_manufacturing": ("制造业 PMI", "%"), "industrial_yoy": ("工业增加值同比", "%"),
    "fai_yoy": ("固定资产投资同比", "%"), "retail_yoy": ("社零同比", "%"),
    "cpi_yoy": ("CPI 同比", "%"), "ppi_yoy": ("PPI 同比", "%"),
    "dr001": ("DR001", "%"), "dr007": ("DR007", "%"),
    "cn_10y": ("中债10Y", "%"), "cn_10y_2y": ("10Y-2Y 利差", "%"),
    "dollar_index": ("美元指数", None), "usd_cny": ("美元兑人民币", None),
    "ted_spread": ("TED 利差", "%"), "hibor_overnight": ("HIBOR 隔夜", "%"),
    "north_today_yi": ("北向当日成交额", "亿"), "north_7d_avg_yi": ("北向7日日均成交额", "亿"),
    "north_7d_change_pct": ("北向7日环比", "%"), "cn_us_10y_spread": ("中美利差(10Y)", "%"),
    "vix": ("VIX", None), "volume": ("两市成交额", "亿"),
    "turnover": ("换手率", "%"), "margin": ("融资融券余额", "亿"),
    "south_net_yi": ("南向净流入", "亿"),
}


class AnalysisSnapshotService:
    def __init__(self, macro_signal_service: MacroSignalService, daily_snapshot_service: DailySnapshotService):
        self._monthly = macro_signal_service
        self._daily = daily_snapshot_service

    def build(self, months: Optional[List[str]], date: Optional[str]) -> Dict[str, Any]:
        requested_months = months or self._monthly.get_available_months()[:1]
        periods = [self._monthly_period(month) for month in requested_months]
        daily = self._daily_snapshot(date)
        missing = [
            indicator["key"] for period in periods for card in period["cards"]
            for indicator in card["indicators"] if indicator["status"] == "missing"
        ] + [
            indicator["key"] for card in daily["cards"] for indicator in card["indicators"]
            if indicator["status"] == "missing"
        ]
        fallbacks = [
            indicator["key"] for card in daily["cards"] for indicator in card["indicators"]
            if indicator["is_asof_fallback"]
        ]
        return {
            "schema_version": "1.0",
            "generated_at": datetime.now().astimezone().isoformat(),
            "request": {"months": requested_months, "date": date},
            "monthly": {"periods": periods},
            "daily": daily,
            "quality": {
                "status": "partial" if missing else "ok",
                "missing_keys": missing,
                "stale_keys": [],
                "asof_fallback_keys": fallbacks,
            },
        }

    def _monthly_period(self, month: str) -> Dict[str, Any]:
        snapshot = self._monthly.get_snapshot(month)
        if snapshot is None:
            return {"month": month, "status": "unavailable", "cards": []}
        cards = []
        for key, title in _MONTHLY_CARDS:
            group = snapshot.groups.get(key)
            indicators = [self._monthly_indicator(indicator) for indicator in (group.indicators if group else [])]
            cards.append({
                "id": key, "title": title, "frequency": "monthly",
                "conclusion": group.conclusion if group else None,
                "score": group.total_score if group else None,
                "status": "ok" if group else "missing",
                "indicators": indicators,
            })
        return {"month": month, "status": "ok", "cards": cards}

    def _daily_snapshot(self, date: Optional[str]) -> Dict[str, Any]:
        snapshot = self._daily.get_daily_snapshot(date)
        as_of = snapshot["date"]
        cards = []
        for card_id, title, group_key in _DAILY_CARDS:
            rows = snapshot["groups"].get(group_key, {}).get("indicators", [])
            cards.append({
                "id": card_id, "title": title, "frequency": "daily", "status": "ok",
                "indicators": [self._daily_indicator(row, as_of) for row in rows],
            })
        return {"as_of": as_of, "cards": cards}

    @staticmethod
    def _meta(key: str) -> tuple[str, Optional[str]]:
        return _INDICATOR_META.get(key, (key, None))

    def _monthly_indicator(self, indicator: Any) -> Dict[str, Any]:
        name, unit = self._meta(indicator.key)
        return {
            "key": indicator.key, "name": name, "unit": unit, "value": indicator.value,
            "previous_value": None, "change": None, "data_date": indicator.data_date,
            "analyzed_at": indicator.analyzed_at, "next_release_at": indicator.next_release_at,
            "next_release_note": indicator.next_release_note, "is_asof_fallback": False,
            "status": "ok" if indicator.value is not None else "missing",
        }

    def _daily_indicator(self, row: Dict[str, Any], as_of: str) -> Dict[str, Any]:
        name, unit = self._meta(row["key"])
        value, previous = row.get("value"), row.get("prev_value")
        return {
            "key": row["key"], "name": name, "unit": unit, "value": value,
            "previous_value": previous,
            "change": value - previous if value is not None and previous is not None else None,
            "data_date": row.get("data_date"), "analyzed_at": None,
            "next_release_at": None, "next_release_note": None,
            "is_asof_fallback": row.get("data_date") is not None and row.get("data_date") != as_of,
            "status": "ok" if value is not None else "missing",
        }


_analysis_snapshot_service: Optional[AnalysisSnapshotService] = None


def get_analysis_snapshot_service() -> AnalysisSnapshotService:
    global _analysis_snapshot_service
    if _analysis_snapshot_service is None:
        from src.services.daily_snapshot_service import get_daily_snapshot_service
        from src.services.macro_signal_service import get_macro_signal_service
        _analysis_snapshot_service = AnalysisSnapshotService(
            get_macro_signal_service(), get_daily_snapshot_service(),
        )
    return _analysis_snapshot_service
