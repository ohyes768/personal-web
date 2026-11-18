"""Per-tab weekly refresh: isolated collector calls and persisted outcomes."""
import json
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Callable

from src.data.market_subtype_map import DISCOVERY_BOND_SUBTYPES, DISCOVERY_STOCK_SUBTYPES
from src.scheduler.tasks import refresh_configured_funds_sync, refresh_stock_funds_sync
from src.services.market_full_pipeline import refresh_market_full_sync
from src.services.sharpe_capture import SharpeRunCapture
from src.utils.config import DATA_DIR
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.weekly")
HISTORY_PATH = DATA_DIR / "scheduler" / "weekly_refresh.jsonl"
TIMEZONE = ZoneInfo("Asia/Shanghai")

# 夏普周榜发布映射（仅两条股基任务发布；bond 两条与普通页面刷新不发布不接
# capture，design「本轮采集与发布」第 6 条）。周键 = 任务开始时刻所在北京时间
# 自然周（recording_week），不用结束时刻。
BOARD_SOURCES = {"stock": "stock", "discovery-stock": "discovery-stock"}
# v3（11-14-sharpe-board-v3-yearly-peer）：同类分位改年度口径，可回溯历史。
# 改回 "v2"/"v1" 即可回滚规则，历史周行按版本隔离互不影响。
BOARD_PROFILE_VERSION = "v3"


def _now() -> str:
    return datetime.now(TIMEZONE).isoformat()


def _new_capture(source: str, run_id: str | None) -> SharpeRunCapture:
    """周刷新 capture：规则条件从带版本固定 profile 填，不读浏览器临时条件。"""
    from src.services import sharpe_board_service as sbs

    profile = sbs.get_profile(source, BOARD_PROFILE_VERSION)
    return SharpeRunCapture(
        run_id=run_id or str(uuid.uuid4()),
        filters=profile["filters"],
        collection_prefilters=profile["collection_prefilters"],
    )


def _publish_capture(
    *, source: str, capture: SharpeRunCapture, trigger: str,
    started_at: datetime, finished_at: datetime,
    profile_version: str = BOARD_PROFILE_VERSION,
) -> str:
    """发布本轮周榜，返回周行状态（complete|failed|skipped_no_new_data）。

    发布失败隔离为 snapshot_status="failed"：不抹掉 collector 成功结果与旧榜，
    不抛出（不阻断队列后续任务）；每次尝试照旧留 JSONL 审计。
    """
    from src.db.session import SessionLocal
    from src.services import sharpe_board_service as sbs

    db = SessionLocal()
    try:
        row, _ = sbs.publish_week_board(
            db, source=source, profile_version=profile_version, capture=capture,
            trigger=trigger, started_at=started_at, finished_at=finished_at,
        )
        return row.status
    except Exception:
        logger.exception(
            "夏普周榜发布失败 source=%s week_start=%s",
            source, sbs.recording_week(started_at),
        )
        return "failed"
    finally:
        db.close()


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
    """Refresh only the selected tab, with page-default market filters.

    stock / discovery-stock 两 tab 额外创建 SharpeRunCapture 透传采集函数，
    完成后发布当前周榜（record.snapshot_status）；scheduled 与 manual 立即
    执行都发布，bond 两条及普通页面刷新不发布。
    """
    start = _now()
    started_at = datetime.now(TIMEZONE)  # 周键取开始时刻，不用结束时刻
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
    board_source = BOARD_SOURCES.get(tab)
    capture = _new_capture(board_source, run_id) if board_source is not None else None
    items = []
    metadata = dict(job_id=job_id, run_id=run_id, trigger=trigger, start=start)
    item = {"tab": tab, "start": start, "status": "running"}
    if on_progress:
        on_progress({**metadata, "status": "running", "items": [item.copy()]})
    logger.info("每周刷新开始 tab=%s", tab)
    try:
        if capture is not None:
            result = refresh(**params, capture=capture)
        else:
            result = refresh(**params)
        item.update(status=classify_result(result), result=result)
    except Exception as exc:
        logger.exception("每周刷新失败 tab=%s", tab)
        item.update(status="failed", error=str(exc))
        if capture is not None:
            # collector 整体崩溃也是输入采集错误：补证据防误发 complete 空榜
            # （capture.errors 恰好为空时，发布侧不能把崩溃当零入选，R6）
            capture.add_error(f"collector crashed: {str(exc)[:150]}")
    item["end"] = _now()
    items.append(item)
    logger.info("每周刷新结束 tab=%s status=%s", tab, item["status"])
    record = dict(**metadata, end=_now(), status=_aggregate([i["status"] for i in items]), items=items)
    if capture is not None:
        # 发布独立于 collector 结果：失败只报告 snapshot_status，不阻断后续任务
        record["snapshot_status"] = _publish_capture(
            source=board_source, capture=capture, trigger=trigger,
            started_at=started_at, finished_at=datetime.now(TIMEZONE),
            profile_version=BOARD_PROFILE_VERSION,
        )
    path = history_path if history_path is not None else HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
