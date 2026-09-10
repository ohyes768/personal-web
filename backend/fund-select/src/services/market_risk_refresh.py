"""
fund_risk_metrics 表 upsert refresh（market tab 风险指标计算）

复用 risk_service.refresh_fund_risks 单只逻辑（已含 fetch_benchmark_tri / fetch_nav），
但只对传入的 codes 跑。

refresh_fund_risks 内部虽再调 fetch_benchmark_tri，但不会写入 fund_benchmark 表；
market tab 必须先 benchmark_refresh.refresh 写入基准行，否则 IR 算不出
（PRD 09-10-market-tab-l4-benchmark-prefetch）。
"""
import json
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import RefreshRun
from src.services import benchmark_refresh
from src.services.risk_service import refresh_fund_risks
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_risk_refresh")


def refresh(session: Session, codes: list[str], task_id: Optional[str] = None) -> dict:
    """对 codes 列表先写基金基准行，再算风险指标，统计 errors。"""
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

    # 先写基金基准行（QDII 写 tri=NULL 跳过行，其他写真实指数），否则 IR 公式读不到基准
    errors.extend(benchmark_refresh.refresh(session, codes))

    # 再算风险指标
    errors.extend(refresh_fund_risks(session, codes))

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
