"""
全市场基金名单 refresh：upsert Fund.name / market_type

关键约束：
- 不动 fund_type（雪球细分类，老 tab 展示用）
- 不动 is_active（akshare 无法判定清盘，MVP 假设全活跃）
- 不动业绩 / 费率 / 持仓 / 风险指标（其他 refresh 流程负责）

按 batch commit（默认 500/批），减少 SQLite lock；RefreshRun 表记录进度。
"""
import json
from datetime import UTC, datetime
from typing import Optional

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db.models import Fund, RefreshRun
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_refresh")

BATCH_SIZE = 500


def refresh(
    session: Session,
    df: pd.DataFrame,
    task_id: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """upsert DataFrame 到 funds 表，返回 {total, inserted, updated, failed, errors, task_id}。

    task_id 非空时同步更新 RefreshRun 进度。
    """
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

    for start in range(0, total, batch_size):
        batch = df.iloc[start:start + batch_size]
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
                if code in existing_codes:
                    session.execute(
                        update(Fund)
                        .where(Fund.code == code)
                        .values(
                            name=row.name,
                            market_type=row.market_type,
                            updated_at=now,
                        )
                    )
                    updated += 1
                else:
                    # 新增：market_type 用 akshare 值；fund_type 留空（雪球数据后续 refresh 填）
                    session.add(Fund(
                        code=code,
                        name=row.name,
                        market_type=row.market_type,
                        fund_type="",
                        is_active=True,
                        updated_at=now,
                    ))
                    inserted += 1
            except Exception as e:  # noqa: BLE001
                session.rollback()
                failed += 1
                if len(errors) < 50:
                    errors.append(f"{code}: {str(e)[:120]}")
                logger.warning("upsert %s 失败: %s", code, str(e)[:120])

        session.commit()

        if run is not None:
            run.completed = min(start + batch_size, total)
            run.failed = failed
            session.commit()

    final_status = "done" if failed == 0 else "error"
    if run is not None:
        _finish_run(session, run, completed=total, failed=failed, errors=errors, final_status=final_status)

    logger.info(
        "market_refresh: total=%d inserted=%d updated=%d failed=%d",
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


def _finish_run(
    session: Session,
    run: RefreshRun,
    completed: int,
    failed: int,
    errors: list[str],
    final_status: str = "done",
) -> None:
    """与 tasks.py._finish_run 行为对齐：写 status / completed / failed / errors / finished_at。"""
    run.status = final_status
    run.completed = completed
    run.failed = failed
    if errors:
        run.errors = json.dumps(errors, ensure_ascii=False)
    run.finished_at = datetime.now(UTC)
    session.commit()
