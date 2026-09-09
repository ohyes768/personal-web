"""
全市场同类排名并发 fetcher（ak.fund_individual_achievement_xq）

单只 ~1.5s，5 worker 并发：4454 × 1.5s / 5 ≈ 22 分钟
写入 fund_achievement_rank 表（按周期多条记录）
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime

import pandas as pd

from src.data.achievement_fetcher import fetch_achievement
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_achievement")

MAX_WORKERS = 5
DELAY_S = 0.2  # 防雪球限流


def fetch_market_achievement(codes: list[str], max_workers: int = MAX_WORKERS,
                              delay_s: float = DELAY_S) -> dict[str, pd.DataFrame]:
    """并发拉全市场同类排名。返回 {code: DataFrame}。

    失败/无数据的 code 不在返回 dict 里（让 refresh 上层只 upsert 有数据的）。
    """
    if not codes:
        return {}

    out: dict[str, pd.DataFrame] = {}
    total = len(codes)
    logger.info("fetch_market_achievement 开始: %d 只 (workers=%d)", total, max_workers)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {executor.submit(_safe_fetch, code, delay_s): code for code in codes}
        done = 0
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            df = future.result()
            if df is not None and not df.empty:
                out[code] = df
            done += 1
            if done % 100 == 0 or done == total:
                logger.info("fetch_market_achievement 进度: %d/%d (%.0f%%) 成功 %d",
                            done, total, 100 * done / total, len(out))

    logger.info("fetch_market_achievement: %d/%d 只成功", len(out), len(codes))
    return out


def _safe_fetch(code: str, delay_s: float) -> pd.DataFrame | None:
    time.sleep(delay_s)
    try:
        return fetch_achievement(code)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_achievement %s 失败: %s", code, str(e)[:120])
        return None
