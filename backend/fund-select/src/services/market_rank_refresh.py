"""
market_fund_rank upsert refresh
"""
import json
from datetime import UTC, datetime
from typing import Optional

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db.models import MarketFundRank, RefreshRun
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_rank_refresh")

BATCH_SIZE = 500


def refresh(session: Session, df: pd.DataFrame, task_id: Optional[str] = None) -> dict:
    """upsert DataFrame 到 market_fund_rank 表。"""
    total = len(df)
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

    for start in range(0, total, BATCH_SIZE):
        batch = df.iloc[start:start + BATCH_SIZE]
        codes = batch["code"].tolist()
        existing_codes = {
            row for row in session.execute(
                select(MarketFundRank.code).where(MarketFundRank.code.in_(codes))
            ).scalars().all()
        }
        now = datetime.now(UTC)

        for row in batch.itertuples(index=False):
            code = row.code
            try:
                values = dict(
                    nav_date=row.nav_date,
                    nav_latest=row.nav_latest,
                    ret_1w=row.ret_1w, ret_1m=row.ret_1m, ret_3m=row.ret_3m,
                    ret_6m=row.ret_6m, ret_1y=row.ret_1y, ret_2y=row.ret_2y,
                    ret_3y=row.ret_3y, ret_ytd=row.ret_ytd, ret_all=row.ret_all,
                    ft_code=row.ft_code, updated_at=now,
                )
                if code in existing_codes:
                    session.execute(
                        update(MarketFundRank).where(MarketFundRank.code == code).values(**values)
                    )
                    updated += 1
                else:
                    session.add(MarketFundRank(code=code, **values))
                    inserted += 1
            except Exception as e:  # noqa: BLE001
                session.rollback()
                failed += 1
                if len(errors) < 50:
                    errors.append(f"{code}: {str(e)[:120]}")
                logger.warning("upsert %s 失败: %s", code, str(e)[:120])

        session.commit()

        if run is not None:
            run.completed = min(start + BATCH_SIZE, total)
            run.failed = failed
            session.commit()

    final_status = "done" if failed == 0 else "error"
    if run is not None:
        _finish_run(session, run, total, failed, errors, final_status=final_status)

    logger.info(
        "market_rank_refresh: total=%d inserted=%d updated=%d failed=%d",
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
