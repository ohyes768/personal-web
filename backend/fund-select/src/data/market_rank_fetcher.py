"""
市场 tab 业绩 fetcher：ak.fund_open_fund_rank_em（天天基金网批量排行榜）

字段映射：
  基金代码 → code
  日期 → nav_date
  单位净值 → nav_latest
  日增长率 → ret_1d
  近1周 → ret_1w, 近1月 → ret_1m, 近3月 → ret_3m, 近6月 → ret_6m
  近1年 → ret_1y, 近2年 → ret_2y, 近3年 → ret_3y
  今年来 → ret_ytd, 成立来 → ret_all
  手续费 → fee_buy

symbol 参数（akshare ft 枚举）：
  股票型 / 混合型 / 债券型 / 指数型 / QDII / LOF / FOF / 货币型 / 理财型

替代之前直接打东财 rankhandler.aspx 的实现（不稳定、易超时、需手写 Referer）。
"""
import time
from datetime import date

import akshare as ak
import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_rank")

PAGE_DELAY_S = 0.5  # 防 akshare 限流

# symbol → market_type 枚举
AKSHARE_SYMBOLS: list[str] = ["股票型", "混合型", "债券型", "指数型", "QDII", "LOF", "FOF", "货币型", "理财型"]


def fetch_market_rank_page(symbol: str, sd: str | None = None, ed: str | None = None,
                            page: int = 1, per_page: int = 5000) -> pd.DataFrame:
    """单 symbol 拉取排行榜。返回 DataFrame[code, name, nav_date, nav_latest, ret_*, ...]。

    akshare fund_open_fund_rank_em 一次性返回该类型全部基金业绩（约 5000 只），
    不需要分页（fund_open_fund_daily_em 同理全市场 24015 只）。
    """
    try:
        df = ak.fund_open_fund_rank_em(symbol=symbol)
    except Exception as e:
        logger.warning("ak.fund_open_fund_rank_em(%s) 失败: %s", symbol, str(e)[:150])
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # 列名标准化
    out = pd.DataFrame({
        "code": df["基金代码"].astype(str).str.zfill(6),
        "name": df["基金简称"].astype(str).str.strip(),
        "nav_date": pd.to_datetime(df["日期"]).dt.date,
        "nav_latest": df["单位净值"].apply(_to_float),
        "acc_nav": df["累计净值"].apply(_to_float),
        "ret_1d": df["日增长率"].apply(_to_float),
        "ret_1w": df["近1周"].apply(_to_float),
        "ret_1m": df["近1月"].apply(_to_float),
        "ret_3m": df["近3月"].apply(_to_float),
        "ret_6m": df["近6月"].apply(_to_float),
        "ret_1y": df["近1年"].apply(_to_float),
        "ret_2y": df["近2年"].apply(_to_float),
        "ret_3y": df["近3年"].apply(_to_float),
        "ret_ytd": df["今年来"].apply(_to_float),
        "ret_all": df["成立来"].apply(_to_float),
        "fee_buy": df["手续费"].astype(str).str.strip(),
        "ft_code": symbol,
    })
    return out


def _to_float(v) -> float | None:
    """float / 百分数字符串 / Series → float；无法解析返回 None"""
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


def fetch_market_rank_bulk(symbols: list[str] | None = None,
                            page_delay_s: float = PAGE_DELAY_S) -> pd.DataFrame:
    """按 symbol 列表分批拉业绩，返回合并 DataFrame。

    默认拉 4 类（股票型 + 混合型 + 债券型 + 指数型）覆盖股基 + 债基 + 混合。
    如需 QDII/FOF/货币型，传 symbols 列表包含。
    """
    if symbols is None:
        symbols = ["股票型", "混合型", "债券型", "指数型", "QDII"]

    all_rows: list[pd.DataFrame] = []
    for sym in symbols:
        df = fetch_market_rank_page(sym)
        if not df.empty:
            all_rows.append(df)
            logger.info("fetch_market_rank_bulk[%s]: %d 只", sym, len(df))
        time.sleep(page_delay_s)

    if not all_rows:
        return pd.DataFrame(columns=[
            "code", "name", "nav_date", "nav_latest", "acc_nav",
            "ret_1d", "ret_1w", "ret_1m", "ret_3m", "ret_6m",
            "ret_1y", "ret_2y", "ret_3y", "ret_ytd", "ret_all",
            "fee_buy", "ft_code",
        ])

    out = pd.concat(all_rows, ignore_index=True)
    out = out.drop_duplicates("code", keep="first").reset_index(drop=True)
    logger.info("fetch_market_rank_bulk 总计: %d 只 (symbols=%s)", len(out), symbols)
    return out