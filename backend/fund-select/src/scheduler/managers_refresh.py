"""经理数据月度全量刷新（2026-11-16 managers-monthly-refresh）。

复用 /api/funds/managers/refresh 手动端点的同一套采集编排
（manager_refresh.refresh(force=True)）与同一把单飞锁 _refresh_lock：
- 手动刷新进行中时，定时轮直接跳过本轮，绝不双跑双份请求
- 采集内置 0.3s 限速 + 指数退避重试（见 manager_profile_fetcher），本模块不加速不加压
- 执行记录写同一份 weekly_refresh.jsonl（按 job_id 过滤），定时任务弹窗历史复用
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.utils.config import DATA_DIR
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.managers_refresh_job")
TIMEZONE = ZoneInfo("Asia/Shanghai")
HISTORY_PATH = DATA_DIR / "scheduler" / "weekly_refresh.jsonl"


def _now() -> str:
    return datetime.now(TIMEZONE).isoformat()


def refresh_managers_sync(
    *, job_id: str, history_path: Path | None = None, trigger: str = "scheduled",
    run_id: str | None = None, on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """经理全量重采（force=True），执行记录落 JSONL 供弹窗历史展示。

    状态口径：采集正常结束但有人失败 → partial（明细在 result.errors）；
    单飞锁被手动刷新占用 → skipped；编排抛异常 → failed。
    """
    from src.api.manager_routes import _refresh_lock
    from src.db.session import SessionLocal
    from src.services.manager_refresh import refresh as refresh_managers

    start = _now()
    metadata = dict(job_id=job_id, run_id=run_id, trigger=trigger, start=start)
    item = {"tab": "managers", "start": start, "status": "running"}
    if on_progress:
        on_progress({**metadata, "status": "running", "items": [item.copy()]})
    logger.info("经理月度刷新开始 trigger=%s", trigger)

    if not _refresh_lock.acquire(blocking=False):
        item.update(status="skipped", end=_now(), error="手动刷新进行中，本轮跳过（避免重复请求）")
        record = {**metadata, "end": _now(), "status": "skipped", "items": [item]}
        _append_history(history_path, record)
        logger.info("经理月度刷新跳过：%s", item["error"])
        return record

    try:
        db = SessionLocal()
        try:
            result = refresh_managers(db, task_id=run_id or str(uuid4()), force=True)
        finally:
            db.close()
        # refresh() 异常才整体失败；正常返回时单人失败已重试 3 次后计入 failed
        status = "success" if result.get("failed", 0) == 0 else "partial"
        item.update(status=status, result=result, end=_now())
    except Exception as exc:  # noqa: BLE001
        logger.exception("经理月度刷新失败")
        item.update(status="failed", error=str(exc)[:300], end=_now())
    finally:
        _refresh_lock.release()

    record = {**metadata, "end": _now(), "status": item["status"], "items": [item]}
    _append_history(history_path, record)
    logger.info("经理月度刷新结束 status=%s", record["status"])
    return record


def _append_history(path: Path | None, record: dict) -> None:
    target = path if path is not None else HISTORY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
