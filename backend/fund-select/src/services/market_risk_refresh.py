"""
fund_risk_metrics 表 upsert refresh（market tab 风险指标计算）

复用 risk_service.refresh_fund_risks 单只逻辑（已含 fetch_benchmark_tri / fetch_nav），
但只对传入的 codes 跑。
"""
import json
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import RefreshRun
from src.services.risk_service import refresh_fund_risks
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_risk_refresh")


def refresh(session: Session, codes: list[str], task_id: Optional[str] = None) -> dict:
    """对 codes 列表调 refresh_fund_risks，统计 errors。"""
    total = len(codes)
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
        return {"task_id": task_id, "total": 0, "completed": 0, "failed": 0, "errors": []}

    # refresh_fund_risks 内部已并发执行每只基金的 benchmark + nav + 计算
    errors = refresh_fund_risks(session, codes)

    failed = len(errors)
    completed = total - failed
    final_status = "done" if failed == 0 else "error"
    if run is not None:
        _finish_run(session, run, completed, failed, errors, final_status=final_status)

    logger.info("market_risk_refresh: total=%d completed=%d failed=%d", total, completed, failed)
    return {
        "task_id": task_id,
        "total": total,
        "completed": completed,
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
