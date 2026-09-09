"""
市场 tab 全量数据 refresh（6 阶段流水线 + 三段预筛）

阶段：
  L0 universe 全市场名单（ak.fund_name_em，5 秒）
  L1 rankhandler 业绩（ak.fund_open_fund_rank_em，50 秒）
  L2 size_yi + age_years（东财 msm 接口，单只 ~0.4s，~10 分钟）
  L3 日频净值 + dd/ret（22 分钟）
  L4 业绩比较基准 + 风险指标（44 分钟）
  L5 同类排名（fund_achievement_xq，22 分钟）

三段预筛（仅接 3 个用户参数）：
  预筛 1：mgr_experience_years（funds 表已有字段，无需 L1 刷新）
  预筛 2：ret_3y + nav_date 常量（market_fund_rank 表字段，需 L1 刷新后）
  预筛 3：size_yi（funds 表字段，需 L2 刷新后；首次刷新时多数 NULL 不过滤）
"""
import json as _json
import uuid as _uuid
from datetime import UTC, date, datetime, timedelta
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

# 净值新鲜度后端常量：A 股工作日 5 天/周 + 节假日 buffer ≈ 14 天
MAX_NAV_STALE_DAYS = 14

from src.data.market_nav_fetcher import fetch_market_nav
from src.data.market_rank_fetcher import fetch_market_rank_bulk
from src.data.market_size_fetcher import fetch_market_size
from src.data.market_subtype_map import (
    DISCOVERY_BOND_SUBTYPES,
    DISCOVERY_STOCK_SUBTYPES,
)
from src.data.market_universe_fetcher import fetch_market_universe
from src.data.market_achievement_fetcher import fetch_market_achievement
from src.db.models import Fund, MarketFundRank, RefreshRun
from src.db.session import SessionLocal
from src.services.market_achievement_refresh import refresh as refresh_market_achievement
from src.services.market_nav_refresh import refresh as refresh_market_nav_db
from src.services.market_rank_refresh import refresh as refresh_market_rank_db
from src.services.market_risk_refresh import refresh as refresh_market_risk_db
from src.services.market_size_refresh import refresh as refresh_market_size_db
from src.services.market_universe_refresh import refresh as refresh_market_universe_db
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_full")


def _load_market_universe(
    session: Session,
    universe_filter: Optional[list[str]] = None,
    min_mgr_exp: Optional[float] = None,
    min_ret_3y: Optional[float] = None,
    max_nav_stale_days: Optional[int] = None,
    min_size_yi: Optional[float] = None,
) -> list[str]:
    """加载股基·市场 + 债基·市场 universe 的 code 列表。

    三段预筛（一个函数实现，所有过滤按需应用）：
      - min_mgr_exp（预筛 1）：funds 表 mgr_experience_years ≥ X 年
        （funds 表字段，未必每只都有，非空才生效）
      - min_ret_3y（预筛 2）：market_fund_rank 表 ret_3y ≥ X%
        （隐式要求成立 ≥ 3 年，NULL 字段过不了 >= X 检查）
      - max_nav_stale_days（预筛 2 附属）：market_fund_rank.nav_date
        距今 ≤ N 天；默认走 MAX_NAV_STALE_DAYS 常量
      - min_size_yi（预筛 3）：funds 表 size_yi ≥ Y 亿
        （funds 表字段，首次刷新多数 NULL，慎用）
    """
    all_types = list(DISCOVERY_BOND_SUBTYPES) + list(DISCOVERY_STOCK_SUBTYPES)
    if universe_filter:
        all_types = [t for t in all_types if t in universe_filter]
    if not all_types:
        return []
    q = select(Fund.code).where(
        Fund.is_active == True,  # noqa: E712
        Fund.market_subtype.in_(all_types),
    )
    # 预筛 1：经理从业（funds 表字段）
    if min_mgr_exp is not None:
        q = q.where(Fund.mgr_experience_years >= min_mgr_exp)
    # 预筛 3：规模（funds 表字段；首次刷新多数 NULL，过滤会砍到 ~0）
    if min_size_yi is not None:
        q = q.where(Fund.size_yi >= min_size_yi)
    codes = list(session.execute(q).scalars().all())
    if not codes:
        return []

    # 预筛 2：L1 业绩字段（基于 market_fund_rank 的 EXISTS 子查询）
    if min_ret_3y is not None or max_nav_stale_days is not None:
        sub = select(MarketFundRank.code).where(MarketFundRank.code == Fund.code)
        if min_ret_3y is not None:
            sub = sub.where(MarketFundRank.ret_3y >= min_ret_3y)
        if max_nav_stale_days is not None:
            cutoff = date.today() - timedelta(days=max_nav_stale_days)
            sub = sub.where(
                or_(MarketFundRank.nav_date.is_(None),
                    MarketFundRank.nav_date >= cutoff)
            )
        q = q.where(sub.exists())
    return list(session.execute(q).scalars().all())


def _run_stage(db: Session, task_id: str, stage_name: str,
               total_codes: int, fn) -> dict:
    """跑单阶段，写进度到 RefreshRun。fn 接受 db 并返回 dict。"""
    import time as _time
    sub_task_id = f"{task_id}_{stage_name}"
    run = RefreshRun(task_id=sub_task_id, status="running", total=total_codes)
    db.add(run)
    db.commit()
    logger.info("▶ 阶段 %s 开始 (total=%d)", stage_name, total_codes)
    _t0 = _time.monotonic()
    try:
        result = fn(db)
        run.status = "done"
        run.completed = total_codes
        run.finished_at = datetime.now(UTC)
        db.commit()
        # 提取关键数字（inserted/updated/failed/completed/total）方便日志看
        if isinstance(result, dict):
            summary = {k: result[k] for k in ("total", "inserted", "updated", "completed", "failed") if k in result}
        else:
            summary = {}
        elapsed = _time.monotonic() - _t0
        logger.info(
            "✓ 阶段 %s 完成 (%.1fs) %s",
            stage_name, elapsed, summary,
        )
        return {"stage": stage_name, "status": "done", "result": result}
    except Exception as e:  # noqa: BLE001
        elapsed = _time.monotonic() - _t0
        logger.exception("✗ 阶段 %s 失败 (%.1fs)", stage_name, elapsed)
        run.status = "error"
        run.errors = _json.dumps([str(e)[:200]], ensure_ascii=False)
        run.finished_at = datetime.now(UTC)
        db.commit()
        return {"stage": stage_name, "status": "error", "error": str(e)[:200]}


def refresh_market_full_sync(
    universe_filter: Optional[list[str]] = None,
    min_ret_3y: Optional[float] = None,
    min_size_yi: Optional[float] = None,
    min_mgr_exp: Optional[float] = None,
    preset_task_id: Optional[str] = None,
) -> dict:
    """市场 tab 全量数据 refresh（5 阶段流水线 + 三段预筛）。

    仅接 3 个用户参数：
      - min_mgr_exp：经理从业 ≥ W 年（预筛 1，funds.mgr_experience_years）
      - min_ret_3y：近 3 年涨跌幅 ≥ X%（预筛 2，market_fund_rank.ret_3y）
      - min_size_yi：规模 ≥ Y 亿（预筛 3，funds.size_yi）

    后端常量：
      - 净值新鲜度 ≤ MAX_NAV_STALE_DAYS = 14 天（不再接用户参数）
    """
    task_id = preset_task_id or str(_uuid.uuid4())
    db = SessionLocal()
    try:
        codes = _load_market_universe(
            db,
            universe_filter,
            min_mgr_exp=min_mgr_exp,
            min_ret_3y=min_ret_3y,
            max_nav_stale_days=MAX_NAV_STALE_DAYS,
            min_size_yi=min_size_yi,
        )
        logger.info(
            "[market_full] task=%s universe=%d (filter=%s min_ret_3y=%s min_size_yi=%s min_mgr_exp=%s max_nav_stale_days=%s)",
            task_id, len(codes), universe_filter,
            min_ret_3y, min_size_yi, min_mgr_exp, MAX_NAV_STALE_DAYS,
        )

        # 创建主 task 的 RefreshRun 记录（前端轮询用）
        from src.db.models import RefreshRun
        from datetime import UTC, datetime
        main_run = RefreshRun(
            task_id=task_id, status="running",
            total=len(codes) * 6 if codes else 6,  # 6 阶段（L0_universe/L1_rank/L2_size/L3_nav/L4_risk/L5_achievement）
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

        # L0 全市场名单（ak.fund_name_em）—— 前置步骤，让 universe 表是最新的
        # 之前需要单独点"刷新"按钮跑这个；现在合并到全量刷新里
        def _stage_l0(d):
            from src.data.market_universe_fetcher import fetch_market_universe
            df = fetch_market_universe()
            return refresh_market_universe_db(d, df, task_id=f"{task_id}_L0")

        stage_results["L0_universe"] = _run_stage(db, task_id, "L0_universe",
                                                   len(codes) or 1, _stage_l0)
        _update_main_progress(len(codes) or 1,
                              failed=stage_results["L0_universe"].get("result", {}).get("failed", 0))

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

        # L2 size_yi + age_years（东财移动端 msm 接口，单只 ~0.4s）
        # 仅对 L1 预筛后 ~1573 只跑，避免拉全 universe 浪费
        def _stage_l2(d):
            rows = fetch_market_size(codes)
            return refresh_market_size_db(d, rows, task_id=f"{task_id}_L2")

        stage_results["L2_size"] = _run_stage(db, task_id, "L2_size",
                                              len(codes), _stage_l2)
        _update_main_progress(len(codes),
                              failed=stage_results["L2_size"].get("result", {}).get("failed", 0))

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

        # L5 同类排名（ak.fund_individual_achievement_xq，每只单只拉 ~1.5s）
        def _stage_l5(d):
            ach_data = fetch_market_achievement(codes)
            return refresh_market_achievement(d, ach_data, task_id=f"{task_id}_L5")

        stage_results["L5_achievement"] = _run_stage(db, task_id, "L5_achievement",
                                                    len(codes), _stage_l5)
        _update_main_progress(len(codes),
                              failed=stage_results["L5_achievement"].get("result", {}).get("failed", 0))

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
