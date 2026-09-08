"""
funds 表基础字段 upsert refresh（fund_basic 拉取结果写库）

只更新：fund_type / established_date / age_years / size_yi / mgr_* 字段
不更新：name / market_subtype / market_type（由 universe refresh 写）
"""
import json
from datetime import UTC, datetime
from typing import Optional

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db.models import Fund, RefreshRun
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_basic_refresh")
BATCH_SIZE = 500


def refresh(session: Session, df: pd.DataFrame, task_id: Optional[str] = None) -> dict:
    """upsert funds 表基础字段。"""
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
                select(Fund.code).where(Fund.code.in_(codes))
            ).scalars().all()
        }
        now = datetime.now(UTC)

        for row in batch.itertuples(index=False):
            code = row.code
            try:
                values = dict(
                    fund_type=row.fund_type or "",
                    established_date=row.established_date,
                    age_years=row.age_years,
                    size_yi=row.size_yi,
                    mgr_name=row.mgr_name,
                    mgr_company=row.mgr_company,
                    mgr_days=row.mgr_days,
                    mgr_experience_years=row.mgr_experience_years,
                    updated_at=now,
                )
                if code in existing_codes:
                    session.execute(
                        update(Fund).where(Fund.code == code).values(**values)
                    )
                    updated += 1
                else:
                    session.add(Fund(
                        code=code,
                        name=row.name or "",
                        is_active=True,
                        **values,
                    ))
                    inserted += 1
            except Exception as e:  # noqa: BLE001
                session.rollback()
                failed += 1
                if len(errors) < 50:
                    errors.append(f"{code}: {str(e)[:120]}")
                logger.warning("upsert basic %s 失败: %s", code, str(e)[:120])

        session.commit()
        if run is not None:
            run.completed = min(start + BATCH_SIZE, total)
            run.failed = failed
            session.commit()

    final_status = "done" if failed == 0 else "error"
    if run is not None:
        _finish_run(session, run, total, failed, errors, final_status=final_status)

    logger.info(
        "market_basic_refresh: total=%d inserted=%d updated=%d failed=%d",
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
