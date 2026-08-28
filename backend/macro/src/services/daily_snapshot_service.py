"""日频快照服务:「信号首页 · 日频」卡片数据组装

从 DataService 的原始 CSV 序列按 asof 语义取「≤ 所选日期最近可得值」。
不走 query_data_by_tab:其 us_treasuries/exchange_rates 段不 reindex 到
union 轴(与 dates 可能不等长),且会组装整 Tab 全字段,这里只要 7 项指标。
"""
from datetime import datetime, time as dtime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.services.data_service import DataService
from src.utils.logger import setup_logger

logger = setup_logger("daily_snapshot_service")

# A股收盘时刻:15:00 前当日盘后数据未发布,默认展示前一交易日
_MARKET_CLOSE = dtime(15, 0)
# 前端日期下拉可选交易日数
_DATES_LIMIT = 60

# 指标清单:dimension → [(前端 key, 序列加载器, CSV 数值列)]
# - key 与前端 constants.ts DAILY_GROUPS / INDICATOR_LABELS 对齐
# - 加载器:'load_data:exchange_rates' 走 DataService.load_data(section),
#   其余为 DataService 上的专用 load 方法名
_DAILY_INDICATORS: Dict[str, List[Tuple[str, str, str]]] = {
    "monetary_policy": [
        ("dr007", "load_dr007", "dr007"),
    ],
    "exchange_rate": [
        ("dollar_index", "load_data:exchange_rates", "美元指数"),
        ("usd_cny", "load_data:exchange_rates", "美元人民币"),
        ("ted_spread", "load_data:ted_spread", "TED利差"),
    ],
    "risk_appetite": [
        ("volume", "load_volume", "total_amount_yi"),
        ("turnover", "load_turnover", "turnover_rate"),
        ("margin", "load_margin", "margin_balance_yi"),
    ],
}


class DailySnapshotService:
    """组装日频快照(3 维度 7 指标)"""

    def __init__(self, data_service: DataService):
        self._ds = data_service

    def get_daily_snapshot(
        self, date: Optional[str] = None, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """取日频快照。

        Args:
            date: 'YYYY-MM-DD';缺省按 15:00 规则推导默认日期
            now: 当前时刻(可注入,测试用);缺省 datetime.now()

        Returns:
            {"date", "dates"(降序), "groups": {dimension: {"indicators": [...]}}}
        """
        now = now or datetime.now()
        today = now.strftime("%Y-%m-%d")

        # 可选日期列表:volume 序列(A股交易日,每交易日必有值)近 60 个 ∪ 今日
        volume_series = self._load_series("load_volume", "total_amount_yi")
        volume_date_strs = (
            volume_series.index.strftime("%Y-%m-%d").tolist() if not volume_series.empty else []
        )
        dates = sorted(set(volume_date_strs[-_DATES_LIMIT:] + [today]), reverse=True)

        effective = date if date else self._default_date(volume_date_strs, today, now)

        groups: Dict[str, Any] = {}
        for dimension, indicators in _DAILY_INDICATORS.items():
            rows = [
                self._extract(self._load_series(loader, column), effective, key)
                for key, loader, column in indicators
            ]
            groups[dimension] = {"indicators": rows}

        logger.info(f"日频快照: date={effective}, dates={len(dates)} 个可选日期")
        return {"date": effective, "dates": dates, "groups": groups}

    def _default_date(
        self, volume_dates: List[str], today: str, now: Optional[datetime] = None
    ) -> str:
        """默认日期:15:00 后取今日(当日未入库时行级 asof 回退并标注);
        15:00 前取今日之前最近的 volume 交易日;volume 无数据兜底今日。"""
        now = now or datetime.now()
        if now.time() >= _MARKET_CLOSE:
            return today
        eligible = [d for d in volume_dates if d < today]
        return eligible[-1] if eligible else today

    def _load_series(self, loader: str, column: str) -> pd.Series:
        """加载单个指标原始序列(index=date 升序、dropna);文件缺失/列缺失返回空 Series"""
        if loader.startswith("load_data:"):
            df = self._ds.load_data(loader.split(":", 1)[1])
        else:
            df = getattr(self._ds, loader)()
        if df.empty or column not in df.columns:
            return pd.Series(dtype=float)
        return df[column].dropna().sort_index()

    @staticmethod
    def _extract(series: pd.Series, target: str, key: str) -> Dict[str, Any]:
        """asof 取 ≤ target 的最后一个值与其前一个有值日(算日变化用)"""
        empty = {"key": key, "value": None, "prev_value": None, "data_date": None}
        if series.empty:
            return empty
        sub = series[series.index <= pd.Timestamp(target)]
        if sub.empty:
            return empty
        return {
            "key": key,
            "value": float(sub.iloc[-1]),
            "prev_value": float(sub.iloc[-2]) if len(sub) >= 2 else None,
            "data_date": sub.index[-1].strftime("%Y-%m-%d"),
        }


# 全局服务实例(与 data_service.get_data_service 同款单例模式)
_daily_snapshot_service: Optional[DailySnapshotService] = None


def get_daily_snapshot_service() -> DailySnapshotService:
    """获取日频快照服务单例"""
    global _daily_snapshot_service
    if _daily_snapshot_service is None:
        from src.services.data_service import get_data_service

        _daily_snapshot_service = DailySnapshotService(data_service=get_data_service())
    return _daily_snapshot_service
