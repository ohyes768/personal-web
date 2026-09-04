"""
空库引导：预研 results_31.csv → SQLite

不联网，让前端不必等第一次刷新就能看表。
"""
import csv
from datetime import UTC, datetime

from src.db.models import Fund, FundFees, FundHoldingsBond, FundPerformance
from src.db.session import SessionLocal, init_db
from src.utils.config import PROJECT_ROOT
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.bootstrap")

BOOTSTRAP_CSV = PROJECT_ROOT.parent / "results_31.csv"


def _f(row: dict, key: str) -> float | None:
    v = (row.get(key) or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _i(row: dict, key: str) -> int | None:
    v = _f(row, key)
    return int(v) if v is not None else None


def bootstrap_from_csv(csv_path=None) -> int:
    """把预研 CSV 灌入库（已存在的 code 跳过）。返回新入库数量。"""
    path = csv_path or BOOTSTRAP_CSV
    if not path.exists():
        logger.error("引导 CSV 不存在: %s", path)
        return 0

    init_db()
    db = SessionLocal()
    added = 0
    try:
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                code = (row.get("code") or "").strip()
                if not code or row.get("ok") != "True":
                    continue
                if db.get(Fund, code):
                    continue

                mgr_days = _i(row, "mgr_days")
                db.add(Fund(
                    code=code,
                    name=row.get("name", ""),
                    fund_type=row.get("fund_type", ""),
                    age_years=_f(row, "age_years"),
                    size_yi=_f(row, "size_yi"),
                    mgr_name=row.get("mgr_name", ""),
                    mgr_company=row.get("mgr_company", ""),
                    mgr_days=mgr_days,
                    mgr_experience_years=round(mgr_days / 365.25, 2) if mgr_days else None,
                    is_active=True,
                ))
                perf = {
                    "code": code,
                    "as_of_date": datetime.now(UTC).date(),
                    "ret_1m": _f(row, "ret_1m"), "ret_6m": _f(row, "ret_6m"),
                    "ret_1y": _f(row, "ret_1y"), "ret_3y": _f(row, "ret_3y"),
                    "ret_5y": _f(row, "ret_5y"),
                    "dd_1y": _f(row, "dd_1y"), "dd_3y": _f(row, "dd_3y"),
                    "dd_5y": _f(row, "dd_5y"),
                }
                if any(v is not None for k, v in perf.items() if k not in ("code", "as_of_date")):
                    db.add(FundPerformance(**perf))

                fees = {
                    "code": code,
                    "fee_buy_small": _f(row, "fee_buy_small"),
                    "fee_redeem_lt7d": _f(row, "fee_redeem_lt7d"),
                    "fee_redeem_7d_1y": _f(row, "fee_redeem_7d_1y"),
                    "fee_redeem_ge1y": _f(row, "fee_redeem_ge1y"),
                    "fee_redeem_ge7d": _f(row, "fee_redeem_ge7d"),
                    "fee_mgmt": _f(row, "fee_mgmt"),
                    "fee_custody": _f(row, "fee_custody"),
                    "fee_service": _f(row, "fee_service"),
                }
                if any(v is not None for k, v in fees.items() if k != "code"):
                    db.add(FundFees(**fees))

                hold_date = (row.get("holdings_as_of") or "").strip()
                hold = {
                    "code": code,
                    "report_date": datetime.strptime(hold_date, "%Y-%m-%d").date() if hold_date else None,
                    "rate_bond_pct": _f(row, "rate_bond_pct"),
                    "credit_bond_pct": _f(row, "credit_bond_pct"),
                    "convertible_pct": _f(row, "convertible_pct"),
                    "top5_concentration": _f(row, "top5_concentration"),
                    "top5_bonds": row.get("top5_bonds", ""),
                }
                if hold["report_date"] is not None:
                    db.add(FundHoldingsBond(**hold))

                added += 1
        db.commit()
        logger.info("CSV 引导完成：%d 只入库", added)
        return added
    except Exception:
        db.rollback()
        logger.exception("CSV 引导失败")
        return 0
    finally:
        db.close()
