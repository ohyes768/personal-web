"""本地重算经理指标（不重新采集）：annualize 口径变更后的回填。

场景：annualize 增加 90 天地板后，已入库的 tenure.annual_return 与
managers 聚合字段（加权年化/最长任期/代表基金）需要按新口径重算。
风险指标（回撤/夏普）不依赖年化，保持原值不动（净值序列不重拉）。

用法：python scripts/recompute_mgr_metrics.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update  # noqa: E402

from src.db.models import Manager, ManagerTenure  # noqa: E402
from src.db.session import SessionLocal, init_db  # noqa: E402
from src.services.manager_metrics import (  # noqa: E402
    annualize,
    pick_representative,
    weighted_annual,
)
from src.utils.logger import setup_logger  # noqa: E402

logger = setup_logger("fund-select.recompute_mgr")


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        mids = db.execute(
            select(Manager.manager_id).where(Manager.fetched_at.isnot(None))
        ).scalars().all()
        logger.info("待重算 %d 名已采经理", len(mids))

        fixed_tenures = 0
        for i, mid in enumerate(mids, 1):
            tenures = db.execute(
                select(ManagerTenure).where(ManagerTenure.manager_id == mid)
            ).scalars().all()
            if not tenures:
                continue
            # 1) 重算每段年化
            dicts = []
            for t in tenures:
                new_ann = annualize(t.tenure_return, t.tenure_days)
                if new_ann != t.annual_return:
                    t.annual_return = new_ann
                    fixed_tenures += 1
                dicts.append({
                    "fund_code": t.fund_code, "fund_name": t.fund_name,
                    "fund_type": t.fund_type, "size_yi": t.size_yi,
                    "start_date": t.start_date.isoformat() if t.start_date else None,
                    "end_date": t.end_date.isoformat() if t.end_date else None,
                    "tenure_days": t.tenure_days, "tenure_return_pct": t.tenure_return,
                    "annual_return": new_ann, "is_current": t.is_current,
                })
            # 2) 重算聚合（风险字段保留原值）
            m = db.get(Manager, mid)
            m.tenure_weighted_annual = weighted_annual(dicts)
            rep = pick_representative(dicts)
            if rep is not None:
                m.representative_fund = rep["fund_code"]
                m.longest_tenure_annual = rep["annual_return"]
                m.longest_tenure_years = (
                    round(rep["tenure_days"] / 365.25, 2) if rep["tenure_days"] else None
                )
            if i % 200 == 0:
                db.commit()
                logger.info("进度 %d/%d", i, len(mids))
        db.commit()
        logger.info("重算完成：%d 段 tenure 年化被置空/修正", fixed_tenures)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
