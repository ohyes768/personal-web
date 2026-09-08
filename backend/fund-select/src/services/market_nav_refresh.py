"""
fund_performance 表 upsert refresh（market tab 日频净值计算结果）

复用 performance_service.compute_performance 计算 ret_*/dd_*
"""
import json
from datetime import UTC, datetime
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import FundPerformance, RefreshRun
from src.services.performance_service import compute_performance
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_nav_refresh")
BATCH_SIZE = 500


def refresh(session: Session, nav_data: dict[str, pd.DataFrame],
            task_id: Optional[str] = None) -> dict:
    """根据日频净值 dict 计算并 upsert fund_performance。"""
    total = len(nav_data)
    inserted = updated = failed = 0
    errors: list[str] = []

    run: RefreshRun | None = None
    if task_id:
        run = session.get(RefreshRun, task_id)
        if run is not None:
            run.total = total
            run.started_at = datetime.now(UTC)
            session.commit()

    if total == 0:
        if run is not None:
            _finish_run(session, run, 0, 0, [], final_status="done")
        return {"task_id": task_id, "total": 0, "inserted": 0, "updated": 0, "failed": 0, "errors": []}

    today = pd.Timestamp.now().normalize()
    codes = list(nav_data.keys())

    for start in range(0, total, BATCH_SIZE):
        batch_codes = codes[start:start + BATCH_SIZE]
        existing_codes = {
            row for row in session.execute(
                select(FundPerformance.code).where(FundPerformance.code.in_(batch_codes))
            ).scalars().all()
        }
        now = datetime.now(UTC)

        for code in batch_codes:
            df = nav_data[code]
            try:
                perf = compute_performance(df, today=today)
                if not perf:
                    # 无业绩数据
                    failed += 1
                    continue
                perf["updated_at"] = now
                if code in existing_codes:
                    session.execute(
                        FundPerformance.__table__.update()
                        .where(FundPerformance.code == code)
                        .values(**perf)
                    )
                    updated += 1
                else:
                    session.add(FundPerformance(code=code, **perf))
                    inserted += 1
            except Exception as e:  # noqa: BLE001
                session.rollback()
                failed += 1
                if len(errors) < 50:
                    errors.append(f"{code}: {str(e)[:120]}")
                logger.warning("upsert nav %s 失败: %s", code, str(e)[:120])

        session.commit()
        if run is not None:
            run.completed = min(start + BATCH_SIZE, total)
            run.failed = failed
            session.commit()

    final_status = "done" if failed == 0 else "error"
    if run is not None:
        _finish_run(session, run, total, failed, errors, final_status=final_status)

    logger.info(
        "market_nav_refresh: total=%d inserted=%d updated=%d failed=%d",
        total, inserted, updated, failed,
    )
    return {
        "task_id": task_id,
        "total": total,
        "inserted": inserted,
        "updated": updated,
        "failed": failed,
        "errors": errors,
    }


def _finish_run(session: Session, run: RefreshRun,
                completed: int, failed: int, errors: list[str],
                final_status: str = "done") -> None:
    run.status = final_status
    run.completed = completed
    run.failed = failed
    if errors:
        run.errors = json.dumps(errors, ensure_ascii=False)
    run.finished_at = datetime.now(UTC)
    session.commit()
