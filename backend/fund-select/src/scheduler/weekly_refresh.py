"""Per-tab weekly refresh: isolated collector calls and persisted outcomes."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Callable

from src.data.market_subtype_map import DISCOVERY_BOND_SUBTYPES, DISCOVERY_STOCK_SUBTYPES
from src.scheduler.tasks import refresh_configured_funds_sync, refresh_stock_funds_sync
from src.services.market_full_pipeline import refresh_market_full_sync
from src.utils.config import DATA_DIR
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.weekly")
HISTORY_PATH = DATA_DIR / "scheduler" / "weekly_refresh.jsonl"
TIMEZONE = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(TIMEZONE).isoformat()


def classify_result(result: dict) -> str:
    """Account for partial failures hidden by a completed pipeline stage."""
    if "stage_results" in result:
        statuses = []
        for stage in result["stage_results"].values():
            if stage.get("status") != "done":
                statuses.append("failed")
            else:
                statuses.append(classify_result(stage.get("result", {})))
        return _aggregate(statuses) if statuses else "failed"
    failed = result.get("failed", 0)
    completed = max(result.get("completed", 0),
                    result.get("inserted", 0) + result.get("updated", 0),
                    result.get("total", 0) - failed)
    if failed:
        return "partial" if completed else "failed"
    if result.get("total") == 0 or result.get("status") == "error":
        return "failed"
    return "success"


def _aggregate(statuses: list[str]) -> str:
    if all(s == "success" for s in statuses):
        return "success"
    if all(s == "failed" for s in statuses):
        return "failed"
    return "partial"


def refresh_tab_sync(
    *, tab: str, job_id: str, history_path: Path | None = None, trigger: str = "scheduled",
    run_id: str | None = None, on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """Refresh only the selected tab, with page-default market filters."""
    start = _now()
    jobs = {
        "bond": (refresh_configured_funds_sync, {"use_cache": False}),
        "stock": (refresh_stock_funds_sync, {"use_cache": False}),
        "discovery-bond": (refresh_market_full_sync, dict(
            universe_filter=list(DISCOVERY_BOND_SUBTYPES), pipeline_profile="bond",
            min_ret_3y=10, min_size_yi=5, min_mgr_exp=5)),
        "discovery-stock": (refresh_market_full_sync, dict(
            universe_filter=list(DISCOVERY_STOCK_SUBTYPES), pipeline_profile="stock",
            min_ret_3y=20, min_size_yi=5, min_mgr_exp=5)),
    }
    refresh, params = jobs[tab]
    items = []
    metadata = dict(job_id=job_id, run_id=run_id, trigger=trigger, start=start)
    item = {"tab": tab, "start": start, "status": "running"}
    if on_progress:
        on_progress({**metadata, "status": "running", "items": [item.copy()]})
    logger.info("每周刷新开始 tab=%s", tab)
    try:
        result = refresh(**params)
        item.update(status=classify_result(result), result=result)
    except Exception as exc:
        logger.exception("每周刷新失败 tab=%s", tab)
        item.update(status="failed", error=str(exc))
    item["end"] = _now()
    items.append(item)
    logger.info("每周刷新结束 tab=%s status=%s", tab, item["status"])
    record = dict(**metadata, end=_now(), status=_aggregate([i["status"] for i in items]), items=items)
    path = history_path if history_path is not None else HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
