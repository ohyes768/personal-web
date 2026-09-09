"""
基金经理数据源：akshare fund_manager_em（全市场经理表，一次拉取）

提供两个接口：
- fetch_manager_table：按姓名聚合 → (mgr_worktime, mgr_company)，服务老 yaml refresh
- fetch_manager_by_fund_code：按「现任基金代码」聚合 → {code: [{name, company, days}, ...]}，
  服务 market_universe_refresh 阶段 0（09-08）
"""
import akshare as ak
import pandas as pd

from src.utils.config import CACHE_DIR
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.manager_fetcher")

CACHE_FILE = CACHE_DIR / "manager_em.json"

# akshare fund_manager_em() 返回列名（中文）
COL_NAME = "姓名"
COL_COMPANY = "所属公司"
COL_FUND_CODE = "现任基金代码"
COL_WORKTIME = "累计从业时间"


def _load_manager_df(use_cache: bool) -> pd.DataFrame:
    """读 akshare 全量经理表（带 JSON 缓存）。失败抛异常。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df: pd.DataFrame | None = None
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

    return df


def fetch_manager_table(use_cache: bool = True) -> tuple[dict[str, int], dict[str, str]]:
    """拉全市场经理表一次。

    Returns:
        (mgr_worktime: 姓名 -> 累计从业天数, mgr_company: 姓名 -> 所属公司)
    """
    df = _load_manager_df(use_cache)

    dedup = df.drop_duplicates(COL_NAME)
    mgr_worktime = dedup.set_index(COL_NAME)[COL_WORKTIME].astype(int).to_dict()
    mgr_company = dedup.set_index(COL_NAME)[COL_COMPANY].astype(str).to_dict()
    return mgr_worktime, mgr_company


def fetch_manager_by_fund_code(
    use_cache: bool = True,
) -> dict[str, list[dict[str, str | int]]]:
    """拉全市场经理表，按「现任基金代码」group by。

    同一经理挂多只基金时，每只都会出现一条记录（用经理自己的 name / company / days）。

    Returns:
        {基金代码 (6 位 str) -> [{"name", "company", "days"}, ...]}
        仅包含至少有一位经理记录的 code；同一 code 内的经理按 akshare 原始顺序。
        同一经理多次出现在同一 code（重复行）时去重，保留首条。
    """
    df = _load_manager_df(use_cache)

    result: dict[str, list[dict[str, str | int]]] = {}
    # 按 现任基金代码 + 姓名 双键去重（避免 akshare 内部重复行）
    seen_keys: set[tuple[str, str]] = set()
    for raw in df.to_dict(orient="records"):
        code = str(raw.get(COL_FUND_CODE, "")).zfill(6)
        name = str(raw.get(COL_NAME, "")).strip()
        if not code or not name:
            continue
        key = (code, name)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        result.setdefault(code, []).append({
            "name": name,
            "company": str(raw.get(COL_COMPANY, "")).strip(),
            "days": int(raw.get(COL_WORKTIME, 0) or 0),
        })

    logger.info(
        "fetch_manager_by_fund_code: %d 个基金代码有经理记录", len(result),
    )
    return result
