"""
无风险利率 fetcher（phase2-A）

主源 bond_zh_us_rate 中国国债 2Y（1990-至今；实测无 1Y 列，2Y 仅高 30~50bp，
不影响 Sharpe 量级）→ fallback macro_china_lpr LPR1Y（月度平铺日频）→ 常量兜底。

单位统一为年化小数（0.021 = 2.1%）。
"""
from datetime import date

import akshare as ak
import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.risk_free_fetcher")

FALLBACK_CONSTANT = 0.025  # 兜底常量（2.5%）


def fetch_risk_free_rate(start: date, end: date) -> pd.DataFrame:
    """日频无风险年化利率。返回 DataFrame[date, rate]（rate 为年化小数）；
    df.attrs["source"] 记录实际数据源。"""
    df = _from_china_gov_2y(start, end)
    if df is not None and not df.empty:
        df.attrs["source"] = "bond_zh_us_rate_2y"
        return df
    logger.warning("国债 2Y 不可用，降级 LPR 1Y")

    df = _from_lpr(start, end)
    if df is not None and not df.empty:
        df.attrs["source"] = "lpr_1y"
        return df
    logger.warning("LPR 不可用，降级常量 %.3f", FALLBACK_CONSTANT)

    dates = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="D")
    df = pd.DataFrame({"date": dates, "rate": [FALLBACK_CONSTANT] * len(dates)})
    df.attrs["source"] = "constant"
    return df


def _from_china_gov_2y(start: date, end: date) -> pd.DataFrame | None:
    try:
        raw = ak.bond_zh_us_rate()
        s = raw.set_index(pd.to_datetime(raw["日期"]))["中国国债收益率2年"].dropna()
        s = (s / 100.0).sort_index()  # 百分比数字 → 小数
        s = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
        return pd.DataFrame({"date": s.index, "rate": s.values})
    except Exception as e:  # noqa: BLE001
        logger.warning("bond_zh_us_rate 失败: %s", str(e)[:120])
        return None


def _from_lpr(start: date, end: date) -> pd.DataFrame | None:
    try:
        raw = ak.macro_china_lpr()
        s = raw.set_index(pd.to_datetime(raw["TRADE_DATE"]))["LPR1Y"].dropna()
        s = (s / 100.0).sort_index()
        # 月度 → 日频前向平铺到窗口
        cal = pd.date_range(max(s.index.min(), pd.Timestamp(start)),
                            min(pd.Timestamp(end), pd.Timestamp.today()))
        s = s.reindex(cal.union(s.index)).sort_index().ffill()
        s = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
        return pd.DataFrame({"date": s.index, "rate": s.values})
    except Exception as e:  # noqa: BLE001
        logger.warning("macro_china_lpr 失败: %s", str(e)[:120])
        return None
