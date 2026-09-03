"""
单只基金快照 + 刷新进度跟踪（移植 fund_screen_31.py 流程）

单只流程：基础信息 → 净值 → [fetch_holdings] 东财季报持仓 → 费率 → [股票型/QDII] 业绩排名
"""
import re
from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy.orm import Session

from src.data.achievement_fetcher import fetch_achievement
from src.data.fee_fetcher import fetch_fees
from src.data.fund_basic_fetcher import _clean, fetch_basic, parse_size
from src.data.holdings_fetcher import analyze_holdings, fetch_bond_hold
from src.data.manager_fetcher import fetch_manager_table
from src.data.nav_fetcher import fetch_nav
from src.db.models import (
    Fund,
    FundAchievementRank,
    FundFees,
    FundHoldingsBond,
    FundPerformance,
)
from src.services.performance_service import compute_performance
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.refresh_service")

# 雪球 achievement_xq 中文列名 → ORM 字段 + 类型。集中维护，新增列只改这里。
ACHIEVEMENT_COLUMNS: dict[str, tuple[str, str]] = {
    "业绩类型": ("period_kind", "text"),
    "周期": ("period", "text"),
    "本产品区间收益": ("ret", "numeric"),
    "本产品最大回撒": ("max_dd", "numeric"),
    "周期收益同类排名": ("peer_rank", "text"),
}


def snapshot_fund(
    code: str,
    mgr_worktime: dict[str, int],
    mgr_company: dict[str, str],
    today: pd.Timestamp | None = None,
    holdings_year: str | None = None,
    fetch_holdings: bool = True,
) -> dict:
    """采集单只基金全量数据，返回待入库 dict。失败抛异常。"""
    out: dict = {"code": code, "achievement": None}
    ref = today if today is not None else pd.Timestamp.now().normalize()
    year = holdings_year or str(ref.year - 1)  # 默认取上一完整年度季报

    # 1. 基础信息
    basic = fetch_basic(code)
    out["name"] = _clean(basic.get("基金名称", ""))
    out["fund_type"] = _clean(basic.get("基金类型", ""))

    est = _clean(basic.get("成立时间", ""))
    if est and est not in ("暂无数据", ""):
        ed = pd.to_datetime(est)
        out["established_date"] = ed.date()
        out["age_years"] = round((ref - ed).days / 365.25, 2)

    out["size_yi"] = parse_size(basic.get("最新规模", ""))

    # 经理：多经理取从业最短（保守估计），公司取第一位命中的
    mgr_name = _clean(basic.get("基金经理", ""))
    out["mgr_name"] = mgr_name
    mgr_days = None
    mgr_co = None
    for name in re.split(r"[、,，\s]+", mgr_name):
        name = name.strip()
        if not name:
            continue
        if name in mgr_worktime:
            d = int(mgr_worktime[name])
            mgr_days = d if mgr_days is None else min(mgr_days, d)
        if mgr_co is None and name in mgr_company:
            mgr_co = mgr_company[name]
    out["mgr_days"] = mgr_days
    out["mgr_experience_years"] = round(mgr_days / 365.25, 2) if mgr_days is not None else None
    out["mgr_company"] = mgr_co

    # 2. 净值 → 业绩
    nav = fetch_nav(code)
    out["performance"] = compute_performance(nav, today=ref)

    # 3. 季报债券持仓（只服务债基筛选的持仓分析；股票宇宙刷新传 fetch_holdings=False 跳过，
    #    避免对无债券持仓披露的基金发无效请求）
    if fetch_holdings:
        tables = fetch_bond_hold(code, year)
        if tables:
            out["holdings"] = {"report_date": date(int(year), 12, 31), **analyze_holdings(tables)}

    # 4. 费率
    out["fees"] = fetch_fees(code)

    # 5. 业绩排名（仅股票型 + QDII，避免对债基空跑）
    fund_type = out["fund_type"]
    if fund_type.startswith("股票型") or fund_type.startswith("QDII") or fund_type == "QDII":
        try:
            ach_df = fetch_achievement(code)
            if not ach_df.empty:
                out["achievement"] = ach_df
                out["achievement_as_of_date"] = ref.date()
        except Exception as e:
            logger.warning("achievement_xq 失败 %s: %s", code, str(e)[:150])

    out["is_active"] = True
    return out


def persist_snapshot(db: Session, snap: dict) -> None:
    """快照 dict 写库（upsert，逐表 commit 由调用方控制）。"""
    code = snap["code"]

    db.merge(Fund(
        code=code,
        name=snap.get("name", ""),
        fund_type=snap.get("fund_type", ""),
        established_date=snap.get("established_date"),
        age_years=snap.get("age_years"),
        size_yi=snap.get("size_yi"),
        mgr_name=snap.get("mgr_name"),
        mgr_company=snap.get("mgr_company"),
        mgr_days=snap.get("mgr_days"),
        mgr_experience_years=snap.get("mgr_experience_years"),
        is_active=snap.get("is_active", True),
        updated_at=datetime.now(UTC),
    ))

    perf = snap.get("performance") or {}
    if perf:
        db.merge(FundPerformance(code=code, updated_at=datetime.now(UTC), **perf))

    fees = snap.get("fees") or {}
    if fees:
        db.merge(FundFees(code=code, updated_at=datetime.now(UTC), **fees))

    hold = snap.get("holdings")
    if hold:
        db.merge(FundHoldingsBond(code=code, updated_at=datetime.now(UTC), **hold))

    # 业绩排名：delete + bulk insert，幂等覆盖
    ach_df = snap.get("achievement")
    if ach_df is not None:
        _replace_achievement(db, code, ach_df, snap["achievement_as_of_date"])


def _replace_achievement(db: Session, code: str, df, as_of_date) -> None:
    """delete 该 code 旧行 + bulk insert 新行。空 df 仅清空。"""
    db.query(FundAchievementRank).filter(FundAchievementRank.code == code).delete()
    if df.empty:
        return
    rows = []
    for _, r in df.iterrows():
        kwargs: dict = {"code": code, "as_of_date": as_of_date}
        for col_zh, (field, kind) in ACHIEVEMENT_COLUMNS.items():
            v = r.get(col_zh)
            if kind == "numeric":
                kwargs[field] = _to_float(v)
            elif field == "peer_rank":
                kwargs[field] = (str(v).strip() if v is not None else "") or None
            else:  # period_kind / period（NOT NULL）
                kwargs[field] = str(v if v is not None else "").strip()
        rows.append(FundAchievementRank(**kwargs))
    db.add_all(rows)


def _to_float(v) -> float | None:
    """雪球 ret/max_dd 可能是 str 或 NaN。"""
    if v is None:
        return None
    try:
        f = float(v)
        from math import isnan
        return None if isnan(f) else f
    except (TypeError, ValueError):
        return None
