"""
market size refresh：upsert funds.size_yi / age_years / established_date / mgr_company

阶段 2（09-09）：用东财移动端 msm 接口 FundMNBasicInformation 单只拉。
仅对 L1 预筛后 ~1573 只运行（不跑全 universe）。

关键不变量：
- size_yi / age_years / established_date：已有非空值**不覆盖**（与 L0 fund_type 保护策略一致）
- mgr_company：始终用 msm 接口的（更准），覆盖 L0 阶段的
"""
import json
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import Fund, RefreshRun
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_size_refresh")

BATCH_SIZE = 100


def refresh(
    session: Session,
    rows: list[dict],
    task_id: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """upsert funds 表的 size_yi / age_years / established_date / mgr_company。

    Args:
        session: SQLAlchemy session
        rows: [{code, established_date, age_years, size_yi, mgr_company}]
        task_id: 非空时同步写 RefreshRun 进度
        batch_size: 每批 commit 行数

    Returns:
        {task_id, total, updated, skipped, failed, errors}
        - updated: 实际写入字段的行数（不区分新增/更新，因 Fund 行必须已存在）
        - skipped: Fund 不存在的 code
        - failed: 处理异常
    """
    total = len(rows)
    updated = skipped = failed = 0
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
            _finish_run(session, run, 0, 0, 0, [], final_status="done")
        return {
            "task_id": task_id, "total": 0, "updated": 0, "skipped": 0,
            "failed": 0, "errors": [],
        }

    now = datetime.now(UTC)

    for start in range(0, total, batch_size):
        batch = rows[start:start + batch_size]
        for r in batch:
            code = r.get("code")
            if not code:
                failed += 1
                continue
            try:
                f = session.get(Fund, code)
                if f is None:
                    skipped += 1
                    continue

                changed = False
                if f.established_date is None and r.get("established_date"):
                    f.established_date = r["established_date"]
                    changed = True
                if f.age_years is None and r.get("age_years") is not None:
                    f.age_years = r["age_years"]
                    changed = True
                if f.size_yi is None and r.get("size_yi") is not None:
                    f.size_yi = r["size_yi"]
                    changed = True
                # mgr_company：始终用 msm 接口的（覆盖 L0 阶段的，更准）
                if r.get("mgr_company"):
                    if f.mgr_company != r["mgr_company"]:
                        f.mgr_company = r["mgr_company"]
                        changed = True

                if changed:
                    f.updated_at = now
                updated += 1
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
        "market_size_refresh: total=%d updated=%d skipped=%d failed=%d",
        total, updated, skipped, failed,
    )
    return {
        "task_id": task_id,
        "total": total,
        "updated": updated,
        "skipped": skipped,
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
