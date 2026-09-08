"""
全市场日频净值并发 fetcher（ak.fund_open_fund_info_em）

复用 fetch_nav()，5 worker 并发：4452 只 / 5 × 1.5s ≈ 22 分钟
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from src.data.nav_fetcher import fetch_nav
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_nav")

MAX_WORKERS = 5
DELAY_S = 0.2


def fetch_market_nav(codes: list[str], max_workers: int = MAX_WORKERS,
                      delay_s: float = DELAY_S) -> dict[str, pd.DataFrame]:
    """并发拉全市场日频净值。返回 {code: DataFrame[净值日期, 日增长率]}。"""
    if not codes:
        return {}

    out: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {executor.submit(_safe_fetch, code, delay_s): code for code in codes}
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            df = future.result()
            if df is not None and not df.empty:
                out[code] = df

    logger.info("fetch_market_nav: %d/%d 只成功", len(out), len(codes))
    return out


def _safe_fetch(code: str, delay_s: float) -> pd.DataFrame | None:
    time.sleep(delay_s)
    try:
        return fetch_nav(code)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_nav %s 失败: %s", code, str(e)[:120])
        return None
