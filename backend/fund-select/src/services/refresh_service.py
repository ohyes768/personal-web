"""
单只基金快照 + 刷新进度跟踪（移植 fund_screen_31.py 流程）

单只流程：基础信息 → 净值 → 东财季报持仓 → 费率（经理表提前一次拉好）
"""
import re
from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy.orm import Session

from src.data.fee_fetcher import fetch_fees
from src.data.fund_basic_fetcher import _clean, fetch_basic, parse_size
from src.data.holdings_fetcher import analyze_holdings, fetch_bond_hold
from src.data.manager_fetcher import fetch_manager_table
from src.data.nav_fetcher import fetch_nav
from src.db.models import Fund, FundFees, FundHoldingsBond, FundPerformance
from src.services.performance_service import compute_performance
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.refresh_service")


def snapshot_fund(
    code: str,
    mgr_worktime: dict[str, int],
    mgr_company: dict[str, str],
    today: pd.Timestamp | None = None,
    holdings_year: str | None = None,
) -> dict:
    """采集单只基金全量数据，返回待入库 dict。失败抛异常。"""
    out: dict = {"code": code}
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

    # 3. 季报债券持仓
    tables = fetch_bond_hold(code, year)
    if tables:
        out["holdings"] = {"report_date": date(int(year), 12, 31), **analyze_holdings(tables)}

    # 4. 费率
    out["fees"] = fetch_fees(code)

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
