"""
fund_achievement_rank 表 upsert refresh（市场 tab 同类排名）

每个 code 多条记录（按周期）；先 delete 旧行再 bulk insert。
"""
import json
from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import FundAchievementRank, RefreshRun
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_achievement_refresh")
BATCH_SIZE = 500


def refresh(session: Session, ach_data: dict[str, "pd.DataFrame"],
            task_id: Optional[str] = None) -> dict:
    """upsert fund_achievement_rank。ach_data: {code: DataFrame}。"""
    total = len(ach_data)
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

    today = date.today()
    for start in range(0, total, BATCH_SIZE):
        batch_codes = list(ach_data.keys())[start:start + BATCH_SIZE]
        for code in batch_codes:
            df = ach_data[code]
            try:
                # 先删该 code 旧行
                session.query(FundAchievementRank).filter(
                    FundAchievementRank.code == code
                ).delete()
                # bulk insert 新行
                for _, r in df.iterrows():
                    session.add(FundAchievementRank(
                        code=code,
                        period_kind=str(r.get("业绩类型", "")).strip() or "未知",
                        period=str(r.get("周期", "")).strip() or "未知",
                        ret=_to_float(r.get("本产品区间收益")),
                        max_dd=_to_float(r.get("本产品最大回撒")),
                        peer_rank=_str_or_none(r.get("周期收益同类排名")),
                        as_of_date=today,
                    ))
                inserted += 1
            except Exception as e:  # noqa: BLE001
                session.rollback()
                failed += 1
                if len(errors) < 50:
                    errors.append(f"{code}: {str(e)[:120]}")
                logger.warning("upsert achievement %s 失败: %s", code, str(e)[:120])
        session.commit()
        if run is not None:
            run.completed = min(start + BATCH_SIZE, total)
            run.failed = failed
            session.commit()

    final_status = "done" if failed == 0 else "error"
    if run is not None:
        _finish_run(session, run, total, failed, errors, final_status=final_status)

    logger.info(
        "market_achievement_refresh: total=%d inserted=%d failed=%d",
        total, inserted, failed,
    )
    return {
        "task_id": task_id,
        "total": total,
        "inserted": inserted,
        "updated": 0,
        "failed": failed,
        "errors": errors,
    }


def _to_float(v) -> float | None:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _str_or_none(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


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
