"""日频快照服务:「信号首页 · 日频」卡片数据组装

从 DataService 的原始 CSV 序列按 asof 语义取「≤ 所选日期最近可得值」。
不走 query_data_by_tab:其 us_treasuries/exchange_rates 段不 reindex 到
union 轴(与 dates 可能不等长),且会组装整 Tab 全字段,这里只要 17 项指标。
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
        ("dr001", "load_dr001", "dr001"),
        ("dr007", "load_dr007", "dr007"),
        ("cn_10y", "load_data:china_bond", "中国10y"),
        ("cn_10y_2y", "load_data:china_bond", "中国10年-2年"),
    ],
    "exchange_rate": [
        ("dollar_index", "load_data:exchange_rates", "美元指数"),
        ("usd_cny", "load_data:exchange_rates", "美元人民币"),
        ("ted_spread", "load_data:ted_spread", "TED利差"),
        ("hibor_overnight", "load_data:hibor", "HIBOR_Overnight"),
        ("north_today_yi", "load_data:fund_flow", "北向成交额"),
        ("north_7d_avg_yi", "load_data:fund_flow", "北向成交额"),
        ("north_7d_change_pct", "load_data:fund_flow", "北向成交额"),
        ("cn_us_10y_spread", "derived:cn_us_10y_spread", ""),
        ("vix", "load_data:vix", "Close_VIX"),
    ],
    "risk_appetite": [
        ("volume", "load_volume", "total_amount_yi"),
        ("turnover", "load_turnover", "turnover_rate"),
        ("margin", "load_margin", "margin_balance_yi"),
        ("south_net_yi", "load_data:fund_flow", "南向净流入"),
    ],
}

# 走 7 日窗口统计而非单点 asof 的指标 key(见 _extract_windowed)
_WINDOWED_KEYS = frozenset({"north_7d_avg_yi", "north_7d_change_pct"})


class DailySnapshotService:
    """组装日频快照(3 维度 17 指标)"""

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
                self._extract_by_key(self._load_series(loader, column), effective, key)
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
        if loader.startswith("derived:"):
            return getattr(self, f"_load_{loader.split(':', 1)[1]}")()
        if loader.startswith("load_data:"):
            df = self._ds.load_data(loader.split(":", 1)[1])
        else:
            df = getattr(self._ds, loader)()
        if df.empty or column not in df.columns:
            return pd.Series(dtype=float)
        return df[column].dropna().sort_index()

    def _load_cn_us_10y_spread(self) -> pd.Series:
        """中美利差(10Y) = 中国10y − 美债10y;美债按中国交易日轴 ffill 对齐后做差"""
        cn = self._load_series("load_data:china_bond", "中国10y")
        us = self._load_series("load_data:us_treasuries", "美债10y")
        if cn.empty or us.empty:
            return pd.Series(dtype=float)
        us_aligned = us.reindex(cn.index, method="ffill")
        return (cn - us_aligned).dropna().sort_index()

    def _extract_by_key(
        self, series: pd.Series, target: str, key: str
    ) -> Dict[str, Any]:
        """按 key 分派提取方式:7 日窗口指标走 _extract_windowed,其余单点 asof"""
        if key in _WINDOWED_KEYS:
            return self._extract_windowed(series, target, key)
        return self._extract(series, target, key)

    @staticmethod
    def _extract_windowed(series: pd.Series, target: str, key: str) -> Dict[str, Any]:
        """7 日窗口指标(基于序列自身交易日,asof ≤ target):

        - north_7d_avg_yi:含 target 的最近 7 个交易日窗口均值;窗口不足 7 日 → value=None
        - north_7d_change_pct:当前窗口均值 vs 前一窗口(第 8~14 交易日)均值的
          百分比变化(×100);任一窗口不足或前窗口均值为 0 → value=None
        - prev_value 恒 None(均值类指标的日变化无意义,环比已有专门指标)
        - data_date = ≤ target 最近可得数据日(数据存在但窗口不足时仍返回,供前端标注)
        """
        empty = {"key": key, "value": None, "prev_value": None, "data_date": None}
        if series.empty:
            return empty
        sub = series[series.index <= pd.Timestamp(target)]
        if sub.empty:
            return empty
        data_date = sub.index[-1].strftime("%Y-%m-%d")
        cur = sub.iloc[-7:]
        if len(cur) < 7:
            return {**empty, "data_date": data_date}
        cur_avg = float(cur.mean())
        if key == "north_7d_avg_yi":
            return {"key": key, "value": cur_avg, "prev_value": None, "data_date": data_date}
        prev = sub.iloc[-14:-7]
        if len(prev) < 7:
            return {"key": key, "value": None, "prev_value": None, "data_date": data_date}
        prev_avg = float(prev.mean())
        value = (cur_avg - prev_avg) / prev_avg * 100 if prev_avg != 0 else None
        return {"key": key, "value": value, "prev_value": None, "data_date": data_date}

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
