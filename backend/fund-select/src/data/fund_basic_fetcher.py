"""
基金基础信息 fetcher（雪球源，移植 fund_screen_31.py）
"""
import re

import akshare as ak
import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.basic_fetcher")


def _clean(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def parse_size(text) -> float | None:
    """'94.51亿' / '12.34万' -> 亿元；无法解析返回 None"""
    t = _clean(text)
    if not t or t == "暂无数据":
        return None
    m = re.match(r"([\d.]+)\s*(亿|万)", t)
    if not m:
        return None
    v = float(m.group(1))
    return v if m.group(2) == "亿" else v / 1e4


def fetch_basic(code: str) -> dict:
    """拉基础信息，返回 item -> value 字典。失败抛异常。"""
    df = ak.fund_individual_basic_info_xq(symbol=code)
    return {row["item"]: row["value"] for _, row in df.iterrows()}
