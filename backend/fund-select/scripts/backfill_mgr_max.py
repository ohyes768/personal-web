"""一次性回填 funds.mgr_days_max / mgr_experience_years_max

背景：共管基金原先只存共管「最短」从业年限，导致「22 年老将 + 3 年新人」
被记成 3 年，min_mgr_exp=5 误杀大量基金（债基 universe 1519 只、股基 526 只）。
新增 *_max 列（共管取最长）作为筛选口径，本脚本用东财经理表重算并回填历史行。

用法：
    python scripts/backfill_mgr_max.py            # 回填
    python scripts/backfill_mgr_max.py --dry-run  # 只看影响面，不写库

幂等：重复执行结果一致（全量按经理表重算，不做增量）。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update  # noqa: E402

from src.data.manager_fetcher import fetch_manager_by_fund_code  # noqa: E402
from src.db.models import Fund  # noqa: E402
from src.db.session import SessionLocal, init_db  # noqa: E402
from src.utils.logger import setup_logger  # noqa: E402

logger = setup_logger("fund-select.backfill_mgr_max")


def main() -> int:
    ap = argparse.ArgumentParser(description="回填共管经理 max 从业年限")
    ap.add_argument("--dry-run", action="store_true", help="只统计影响面，不写库")
    ap.add_argument("--no-cache", action="store_true", help="忽略缓存，强制重拉经理表")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    try:
        logger.info("拉取经理表…")
        mgr_by_code = fetch_manager_by_fund_code(use_cache=not args.no_cache)
        logger.info("经理表覆盖 %d 个基金代码", len(mgr_by_code))

        rows = db.execute(
            select(Fund.code, Fund.mgr_experience_years, Fund.mgr_experience_years_max)
        ).all()

        to_fill = []       # (code, days_max, years_max)
        rescued = []       # 原先被 min 判死、现已达标的基金
        for code, cur_years, cur_max in rows:
            mgrs = mgr_by_code.get(code) or []
            days = [int(m["days"]) for m in mgrs if m.get("days") is not None]
            if not days:
                continue
            days_max = max(days)
            years_max = round(days_max / 365.25, 2)
            to_fill.append((code, days_max, years_max))
            if cur_years is not None and cur_years < 5 <= years_max:
                rescued.append(code)

        logger.info(
            "待回填 %d 行；其中「原 min<5 年但 max≥5 年」被救回 %d 只",
            len(to_fill), len(rescued),
        )

        if args.dry_run:
            logger.info("--dry-run：不写库")
            for code in rescued[:10]:
                logger.info("  救回示例 %s", code)
            return 0

        for code, days_max, years_max in to_fill:
            db.execute(
                update(Fund)
                .where(Fund.code == code)
                .values(mgr_days_max=days_max, mgr_experience_years_max=years_max)
            )
        db.commit()
        logger.info("回填完成：%d 行", len(to_fill))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
