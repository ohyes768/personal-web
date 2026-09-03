"""
历史净值 fetcher（东财源，移植 fund_screen_31.py）
"""
import akshare as ak
import pandas as pd


def fetch_nav(code: str) -> pd.DataFrame:
    """拉历史单位净值，按日期升序。失败抛异常；无数据返回空 DataFrame。

    「日增长率」为东财官方日涨跌幅：数值列（float，百分数如 0.31 = 0.31%），
    分红日已作除息调整 → /100 即复权日收益。勿用累计净值 pct_change 算收益
    （累计净值 = 单位净值 + 历史分红简单加总，非复权，分红基金会稀释全序列）。
    """
    df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
    if df.empty:
        return df
    df["净值日期"] = pd.to_datetime(df["净值日期"])
    df["日增长率"] = df["日增长率"].astype(float)
    return df.sort_values("净值日期").reset_index(drop=True)
