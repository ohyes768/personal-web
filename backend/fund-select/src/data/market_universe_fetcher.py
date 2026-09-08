"""
全市场基金名单 fetcher：ak.fund_name_em() 一次拉取

数据源：天天基金网 fundcode_search.js（东方财富）
字段：基金代码 / 拼音缩写 / 基金简称 / 基金类型 / 拼音全称

基金类型是「粗分类-子类」拼接（27 个枚举值，如 股票型、债券型-中短债、指数型-固收、
QDII-普通股票）。子类精确映射到 tab 分类（bond / stock / other）由
`market_subtype_map.SUBCLASS_TO_CATEGORY` 维护。
"""
import akshare as ak
import pandas as pd

from src.data.market_subtype_map import categorize
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_universe")

EXPECTED_OUTPUT_COLUMNS = ["code", "name", "market_subtype", "market_type"]


def fetch_market_universe() -> pd.DataFrame:
    """调 ak.fund_name_em() 一次拉全市场基金（约 2.8 万只），返回标准化 DataFrame。

    返回列：code (str, 6位) / name (str) / market_subtype (str, akshare 原值) /
            market_type (str, 'bond' / 'stock' / 'other')
    失败抛异常（外层调度重试）。空结果返回空 DataFrame（标准列）。
    """
    df = ak.fund_name_em()
    if df is None or df.empty:
        logger.warning("ak.fund_name_em() 返回空结果")
        return pd.DataFrame(columns=EXPECTED_OUTPUT_COLUMNS)

    try:
        out = pd.DataFrame({
            "code": df["基金代码"].astype(str).str.zfill(6),
            "name": df["基金简称"].astype(str).str.strip(),
            "market_subtype": df["基金类型"].astype(str).str.strip(),
        })
    except KeyError as e:
        # akshare 接口列名变更
        logger.error("ak.fund_name_em() 返回列名变更: %s", e)
        raise

    out["market_type"] = out["market_subtype"].map(categorize)

    # 去重（按 code 唯一）；保留首条
    out = out.drop_duplicates("code", keep="first").reset_index(drop=True)
    logger.info(
        "fetch_market_universe: %d 只 (stock=%d bond=%d other=%d unknown_subtype=%d)",
        len(out),
        (out["market_type"] == "stock").sum(),
        (out["market_type"] == "bond").sum(),
        (out["market_type"] == "other").sum(),
        (out["market_subtype"] == "").sum(),
    )
    return out
