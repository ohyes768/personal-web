"""
市场 tab 全量数据 refresh（4 阶段流水线）

阶段：
  L1 rankhandler 业绩 (50 秒, 全 universe 不筛)
  L2 fund_basic 经理/类型 (30 分钟, 用 universe 过滤)
  L3 日频净值 + dd/ret (22 分钟, 用 universe 过滤)
  L4 业绩比较基准 + 风险指标 (44 分钟, 用 universe 过滤)
"""
import json as _json
import uuid as _uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data.market_basic_fetcher import fetch_market_basic
from src.data.market_nav_fetcher import fetch_market_nav
from src.data.market_rank_fetcher import fetch_market_rank_bulk
from src.data.market_subtype_map import (
    DISCOVERY_BOND_SUBTYPES,
    DISCOVERY_STOCK_SUBTYPES,
)
from src.db.models import Fund, RefreshRun
from src.db.session import SessionLocal
from src.services.market_basic_refresh import refresh as refresh_market_basic_db
from src.services.market_nav_refresh import refresh as refresh_market_nav_db
from src.services.market_rank_refresh import refresh as refresh_market_rank_db
from src.services.market_risk_refresh import refresh as refresh_market_risk_db
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_full")


def _load_market_universe(
    session: Session,
    universe_filter: Optional[list[str]] = None,
    min_age: Optional[float] = None,
    min_size_yi: Optional[float] = None,
) -> list[str]:
    """加载股基·市场 + 债基·市场 universe 的 code 列表（SQL 预过滤）。"""
    all_types = list(DISCOVERY_BOND_SUBTYPES) + list(DISCOVERY_STOCK_SUBTYPES)
    if universe_filter:
        all_types = [t for t in all_types if t in universe_filter]
    if not all_types:
        return []
    q = select(Fund.code).where(
        Fund.is_active == True,  # noqa: E712
        Fund.market_subtype.in_(all_types),
    )
    if min_age is not None:
        q = q.where(Fund.age_years >= min_age)
    if min_size_yi is not None:
        q = q.where(Fund.size_yi >= min_size_yi)
    return list(session.execute(q).scalars().all())


def _run_stage(db: Session, task_id: str, stage_name: str,
               total_codes: int, fn) -> dict:
    """跑单阶段，写进度到 RefreshRun。fn 接受 db 并返回 dict。"""
    sub_task_id = f"{task_id}_{stage_name}"
    run = RefreshRun(task_id=sub_task_id, status="running", total=total_codes)
    db.add(run)
    db.commit()
    try:
        result = fn(db)
        run.status = "done"
        run.completed = total_codes
        run.finished_at = datetime.now(UTC)
        db.commit()
        return {"stage": stage_name, "status": "done", "result": result}
    except Exception as e:  # noqa: BLE001
        logger.exception("stage %s 失败", stage_name)
        run.status = "error"
        run.errors = _json.dumps([str(e)[:200]], ensure_ascii=False)
        run.finished_at = datetime.now(UTC)
        db.commit()
        return {"stage": stage_name, "status": "error", "error": str(e)[:200]}


def refresh_market_full_sync(
    universe_filter: Optional[list[str]] = None,
    min_age: Optional[float] = None,
    min_size_yi: Optional[float] = None,
    preset_task_id: Optional[str] = None,
) -> dict:
    """市场 tab 全量数据 refresh（4 阶段流水线）。

    参数：
      universe_filter: market_subtype 子集（None = 全 universe）
      min_age / min_size_yi: SQL 预过滤（用户传入）

    返回：
      {
        task_id, universe_size, stage_results: {
          "L1_rank": {...}, "L2_basic": {...}, "L3_nav": {...}, "L4_risk": {...}
        }
      }
    """
    task_id = preset_task_id or str(_uuid.uuid4())
    db = SessionLocal()
    try:
        codes = _load_market_universe(db, universe_filter, min_age, min_size_yi)
        logger.info(
            "[market_full] task=%s universe=%d (filter=%s min_age=%s min_size_yi=%s)",
            task_id, len(codes), universe_filter, min_age, min_size_yi,
        )

        # 创建主 task 的 RefreshRun 记录（前端轮询用）
        from src.db.models import RefreshRun
        from datetime import UTC, datetime
        main_run = RefreshRun(
            task_id=task_id, status="running",
            total=len(codes) * 4 if codes else 4,  # 4 阶段总和（用于粗略进度）
            completed=0, failed=0,
            started_at=datetime.now(UTC),
        )
        db.add(main_run)
        db.commit()

        stage_results = {}

        def _update_main_progress(stage_done_codes: int, failed: int = 0):
            """每阶段完成后更新主 task 进度（粗略聚合）"""
            main_run.completed += stage_done_codes
            main_run.failed += failed
            db.commit()

        # L1 rankhandler 业绩（用 akshare fund_open_fund_rank_em，单类全量返回）
        def _stage_l1(d):
            df = fetch_market_rank_bulk(
                symbols=["股票型", "混合型", "债券型", "指数型", "QDII"],
            )
            return refresh_market_rank_db(d, df, task_id=f"{task_id}_L1")

        stage_results["L1_rank"] = _run_stage(db, task_id, "L1_rank",
                                              len(codes) or 1, _stage_l1)
        _update_main_progress(len(codes) or 1,
                              failed=stage_results["L1_rank"].get("result", {}).get("failed", 0))

        # L2 fund_basic 经理/类型
        def _stage_l2(d):
            df = fetch_market_basic(codes)
            return refresh_market_basic_db(d, df, task_id=f"{task_id}_L2")

        stage_results["L2_basic"] = _run_stage(db, task_id, "L2_basic",
                                                len(codes), _stage_l2)
        _update_main_progress(len(codes),
                              failed=stage_results["L2_basic"].get("result", {}).get("failed", 0))

        # L3 日频净值 + dd/ret
        def _stage_l3(d):
            nav_data = fetch_market_nav(codes)
            return refresh_market_nav_db(d, nav_data, task_id=f"{task_id}_L3")

        stage_results["L3_nav"] = _run_stage(db, task_id, "L3_nav",
                                              len(codes), _stage_l3)
        _update_main_progress(len(codes),
                              failed=stage_results["L3_nav"].get("result", {}).get("failed", 0))

        # L4 业绩比较基准 + 风险指标
        def _stage_l4(d):
            return refresh_market_risk_db(d, codes, task_id=f"{task_id}_L4")

        stage_results["L4_risk"] = _run_stage(db, task_id, "L4_risk",
                                                len(codes), _stage_l4)
        _update_main_progress(len(codes),
                              failed=stage_results["L4_risk"].get("result", {}).get("failed", 0))

        # 主 task 标记完成
        main_run.status = "done" if all(
            r.get("status") == "done" for r in stage_results.values()
        ) else "error"
        main_run.finished_at = datetime.now(UTC)
        db.commit()

        return {
            "task_id": task_id,
            "universe_size": len(codes),
            "stage_results": stage_results,
        }
    finally:
        db.close()
