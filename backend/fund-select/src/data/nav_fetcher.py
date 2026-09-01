"""
历史净值 fetcher（东财源，移植 fund_screen_31.py）
"""
import akshare as ak
import pandas as pd


def fetch_nav(code: str) -> pd.DataFrame:
    """拉历史单位净值，按日期升序。失败抛异常；无数据返回空 DataFrame。"""
    df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
    if df.empty:
        return df
    df["净值日期"] = pd.to_datetime(df["净值日期"])
    return df.sort_values("净值日期").reset_index(drop=True)
