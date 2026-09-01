"""
业绩计算：净值窗口收益 / 最大回撤（移植 fund_screen_31.py 算法）
"""
import pandas as pd

# 窗口定义：字段后缀 -> 天数
PERIODS = {
    "1m": 30,
    "6m": 180,
    "1y": 365,
    "3y": 365 * 3,
    "5y": 365 * 5,
}


def period_return(nav: pd.DataFrame, days: int, today: pd.Timestamp | None = None) -> float | None:
    """过去 N 天累计收益率（%）。基准日 = 今天；today 可注入便于测试。"""
    if nav is None or nav.empty:
        return None
    ref = today if today is not None else pd.Timestamp.now().normalize()
    cutoff = ref - pd.Timedelta(days=days)
    then = nav[nav["净值日期"] <= cutoff]
    if then.empty:
        return None
    nv_now = float(nav.iloc[-1]["单位净值"])
    nv_then = float(then.iloc[-1]["单位净值"])
    if nv_then <= 0:
        return None
    return round((nv_now / nv_then - 1) * 100, 2)


def max_drawdown(nav: pd.DataFrame, days: int, today: pd.Timestamp | None = None) -> float | None:
    """过去 N 天最大回撤（%，负值）。窗口不足 2 条返回 None。"""
    if nav is None or nav.empty:
        return None
    ref = today if today is not None else pd.Timestamp.now().normalize()
    cutoff = ref - pd.Timedelta(days=days)
    window = nav[nav["净值日期"] >= cutoff]
    if len(window) < 2:
        return None
    nv = window["单位净值"].astype(float)
    dd = (nv - nv.cummax()) / nv.cummax() * 100
    return round(float(dd.min()), 2)


def compute_performance(nav: pd.DataFrame, today: pd.Timestamp | None = None) -> dict:
    """一次算齐所有窗口的收益 + 回撤 + 最新净值。"""
    out: dict = {}
    if nav is None or nav.empty:
        return out
    ref = today if today is not None else pd.Timestamp.now().normalize()
    out["as_of_date"] = ref.date()
    out["nav_latest"] = float(nav.iloc[-1]["单位净值"])
    out["nav_date"] = nav.iloc[-1]["净值日期"].date()
    for key, days in PERIODS.items():
        r = period_return(nav, days, today=ref)
        dd = max_drawdown(nav, days, today=ref)
        if r is not None:
            out[f"ret_{key}"] = r
        if dd is not None and key in ("1y", "3y", "5y"):  # 库表只存 1y/3y/5y 回撤
            out[f"dd_{key}"] = dd
    return out
