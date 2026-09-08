"""
全市场基金名单 fetcher：ak.fund_name_em() 一次拉取

数据源：天天基金网 fundcode_search.js（东方财富）
字段：基金代码 / 拼音缩写 / 基金简称 / 基金类型 / 拼音全称

基金类型是粗粒度枚举：债券型 / 股票型 / 混合型 / 货币型 / 指数型 / QDII / FOF / 定开债券 / ...
二级分类（"中长期纯债 / 短期纯债 / 可转债"）需逐只拉雪球，超出 MVP 范围。
"""
import akshare as ak
import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_universe")

EXPECTED_OUTPUT_COLUMNS = ["code", "name", "market_type"]


def fetch_market_universe() -> pd.DataFrame:
    """调 ak.fund_name_em() 一次拉全市场基金（约 1 万只），返回标准化 DataFrame。

    返回列：code (str, 6位) / name (str) / market_type (str)
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
            "market_type": df["基金类型"].astype(str).str.strip(),
        })
    except KeyError as e:
        # akshare 接口列名变更
        logger.error("ak.fund_name_em() 返回列名变更: %s", e)
        raise

    # 去重（按 code 唯一）；保留首条
    out = out.drop_duplicates("code", keep="first").reset_index(drop=True)
    logger.info("fetch_market_universe: %d 只", len(out))
    return out
