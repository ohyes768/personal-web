"""
基金经理数据源：akshare fund_manager_em（全市场经理表，一次拉取）
"""
from pathlib import Path

import akshare as ak
import pandas as pd

from src.utils.config import CACHE_DIR
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.manager_fetcher")

CACHE_FILE = CACHE_DIR / "manager_em.json"


def fetch_manager_table(use_cache: bool = True) -> tuple[dict[str, int], dict[str, str]]:
    """拉全市场经理表一次。

    Returns:
        (mgr_worktime: 姓名 -> 累计从业天数, mgr_company: 姓名 -> 所属公司)
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = None
    if use_cache and CACHE_FILE.exists():
        try:
            cached = pd.read_json(CACHE_FILE)
            if not cached.empty:
                df = cached
                logger.info("经理表使用缓存: %d 条", len(df))
        except Exception:
            logger.warning("经理表缓存损坏，重新拉取")

    if df is None:
        df = ak.fund_manager_em()
        try:
            df.to_json(CACHE_FILE, orient="records", force_ascii=False)
        except Exception:
            logger.warning("经理表缓存写入失败（不影响流程）")

    dedup = df.drop_duplicates("姓名")
    mgr_worktime = dedup.set_index("姓名")["累计从业时间"].astype(int).to_dict()
    mgr_company = dedup.set_index("姓名")["所属公司"].astype(str).to_dict()
    return mgr_worktime, mgr_company
