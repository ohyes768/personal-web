"""
业绩排名 fetcher（雪球源，移植 fund_screen_31.py 风格）

返回 DataFrame（雪球原样）：
    columns = [业绩类型, 周期, 本产品区间收益, 本产品最大回撒, 周期收益同类排名]

失败抛异常；无数据返回空 DataFrame。
"""
import akshare as ak
import pandas as pd


def fetch_achievement(code: str) -> pd.DataFrame:
    """拉业绩排名（按周期）。失败抛异常；无数据返回空 DataFrame。"""
    return ak.fund_individual_achievement_xq(symbol=code)
