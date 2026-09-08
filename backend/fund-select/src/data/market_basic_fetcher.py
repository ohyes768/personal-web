"""
全市场 fund_basic 并发 fetcher（雪球 ak.fund_individual_basic_info_xq）

复用现有 fetch_basic()，5 worker 并发：4452 只 / 5 × 2s ≈ 30 分钟
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import pandas as pd

from src.data.fund_basic_fetcher import _clean, fetch_basic, parse_size
from src.data.manager_fetcher import fetch_manager_table
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_basic")

MAX_WORKERS = 5
DELAY_S = 0.2  # 防雪球限流


def fetch_market_basic(codes: list[str], max_workers: int = MAX_WORKERS,
                        delay_s: float = DELAY_S,
                        use_mgr_cache: bool = True) -> pd.DataFrame:
    """并发拉全市场 fund_basic，返回 [code, name, fund_type, established_date,
    age_years, size_yi, mgr_name, mgr_company, mgr_days, mgr_experience_years]"""
    if not codes:
        return pd.DataFrame()

    # 经理表一次拉取（缓存命中即可）
    mgr_worktime, mgr_company = fetch_manager_table(use_cache=use_mgr_cache)

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {
            executor.submit(_safe_fetch, code, delay_s, mgr_worktime, mgr_company): code
            for code in codes
        }
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            data = future.result()
            if data is not None:
                rows.append(data)

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates("code", keep="first").reset_index(drop=True)
    logger.info("fetch_market_basic: %d/%d 只成功", len(df), len(codes))
    return df


def _safe_fetch(code: str, delay_s: float,
                mgr_worktime: dict[str, int],
                mgr_company: dict[str, str]) -> dict | None:
    """单只 fetch_basic + 字段标准化。失败返回 None。"""
    time.sleep(delay_s)
    try:
        info = fetch_basic(code)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_basic %s 失败: %s", code, str(e)[:120])
        return None

    name = _clean(info.get("基金名称", ""))
    fund_type = _clean(info.get("基金类型", ""))
    est = _clean(info.get("成立时间", ""))
    established_date = None
    age_years = None
    if est and est not in ("暂无数据", ""):
        try:
            from datetime import datetime as _dt
            ed = _dt.fromisoformat(est)
            established_date = ed.date()
            age_years = round((_dt.now() - ed).days / 365.25, 2)
        except ValueError:
            pass

    size_yi = parse_size(info.get("最新规模", ""))

    mgr_name = _clean(info.get("基金经理", ""))
    mgr_days = None
    mgr_co = None
    if mgr_name:
        import re
        for name_part in re.split(r"[、,，\s]+", mgr_name):
            name_part = name_part.strip()
            if not name_part:
                continue
            if name_part in mgr_worktime:
                d = int(mgr_worktime[name_part])
                mgr_days = d if mgr_days is None else min(mgr_days, d)
            if mgr_co is None and name_part in mgr_company:
                mgr_co = mgr_company[name_part]
    mgr_experience_years = round(mgr_days / 365.25, 2) if mgr_days is not None else None

    return {
        "code": code,
        "name": name,
        "fund_type": fund_type,
        "established_date": established_date,
        "age_years": age_years,
        "size_yi": size_yi,
        "mgr_name": mgr_name or None,
        "mgr_company": mgr_co,
        "mgr_days": mgr_days,
        "mgr_experience_years": mgr_experience_years,
    }
