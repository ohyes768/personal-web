"""经理数据采集编排（M0-M4，任务 11-10-fund-manager-evaluation）。

- M0 全市场经理表 → managers 骨架（ID 主键）
- M1 库内主动权益基金 → 经理名 → ID 映射，过滤出首版 scope 集合
- M2 逐人档案页 → manager_tenures（限速 + 重试 + 断点续采）
- M3 代表基金复权序列 → 风险指标
- M4 聚合 managers 业绩字段

断点续采：managers.fetched_at IS NULL 视为待采；每采完一人 commit 一次。
RefreshRun 记进度（复用现有机制，task_id 前缀 manager_refresh）。
"""
from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.data.manager_profile_fetcher import (
    fetch_adjusted_series,
    fetch_manager_table_with_id,
    fetch_manager_tenures,
)
from src.db.models import Fund, Manager, ManagerTenure, RefreshRun
from src.services.manager_metrics import (
    annualize,
    compute_risk,
    pick_representative,
    slice_series,
    weighted_annual,
)
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.manager_refresh")

BATCH_LOG_EVERY = 50
BATCH_COMMIT_EVERY = 20
# 进度落库批次：比 BATCH_COMMIT_EVERY 更密，进度条才跟得上一人 ~0.3s 的节奏；
# 只 commit 不重置，代价是每人一次 SQLite 写，与采集耗时相比可忽略。
PROGRESS_COMMIT_EVERY = 5


def refresh(
    session: Session,
    task_id: Optional[str] = None,
    profile_fetch_delay_s: float = 0.3,
    max_managers: Optional[int] = None,
    fetch_nav: bool = True,
    table_provider=fetch_manager_table_with_id,
    tenure_provider=fetch_manager_tenures,
    nav_provider=fetch_adjusted_series,
    active_codes_provider=None,
    force: bool = False,
) -> dict:
    """全量采集 + 聚合。providers 可注入以便测试 mock。

    Args:
        active_codes_provider: () -> set[str]，库内主动权益基金代码集合；
            None 则实时查 funds 表。
        force: True = 重采 scope 内全部经理（覆盖档案变更：新增/离任/规模调整）；
            False = 断点续采，只采 fetched_at IS NULL 的（首采/中断续采）。
    """
    run: RefreshRun | None = None
    if task_id:
        run = session.get(RefreshRun, task_id)
        if run is None:
            run = RefreshRun(task_id=task_id, status="running")
            session.add(run)
        run.status = "running"
        run.started_at = datetime.now(UTC)
        session.commit()

    stats = {"managers_total": 0, "tenures_total": 0, "failed": 0,
             "errors": [], "risk_computed": 0}

    try:
        # ── M0 经理表 → managers 骨架 ──
        table = table_provider()
        logger.info("M0 经理表 %d 人", len(table))
        for row in table:
            mgr = session.get(Manager, row["manager_id"])
            if mgr is None:
                mgr = Manager(manager_id=row["manager_id"], name=row["name"])
                session.add(mgr)
            mgr.name = row["name"]
            mgr.company = row["company"] or None
            mgr.career_days = row["career_days"]
            mgr.career_years = round(row["career_days"] / 365.25, 2) if row["career_days"] else None
            mgr.current_scale_yi = row["current_scale_yi"]
            mgr.current_fund_count = len(row["fund_codes"])
            mgr.updated_at = datetime.now(UTC)
        session.commit()
        stats["managers_total"] = len(table)

        # ── M1 库内主动权益 → scope 集合 ──
        active_codes = (
            set(active_codes_provider()) if active_codes_provider
            else _load_active_equity_codes(session)
        )
        code_to_ids = {
            row["manager_id"]: set(row["fund_codes"]) & active_codes
            for row in table
        }
        scoped_ids = {
            mid for mid, codes in code_to_ids.items() if codes
        }
        # 保留已采集过的（scope 内）+ 本次命中的；scope 外的经理行保留骨架但不采档案
        logger.info("M1 库内主动权益 %d 只基金，涉及经理 %d 人", len(active_codes), len(scoped_ids))

        pending_ids = (list(scoped_ids) if force
                       else [mid for mid in scoped_ids if _needs_fetch(session, mid)])
        if max_managers is not None:
            pending_ids = pending_ids[:max_managers]
        logger.info("M2 待采档案 %d / %d 人（force=%s）", len(pending_ids), len(scoped_ids), force)

        # 进度分母：本轮待采人数（页面进度条用 completed/total）
        if run is not None:
            run.total = len(pending_ids)
            session.commit()

        # ── M2/M3/M4 逐人采集与聚合 ──
        done = 0
        for mid in pending_ids:
            try:
                tenures = tenure_provider(mid)
                _replace_tenures(session, mid, tenures)
                stats["tenures_total"] += len(tenures)
            except Exception as e:  # noqa: BLE001
                stats["failed"] += 1
                if len(stats["errors"]) < 50:
                    stats["errors"].append(f"{mid}: {str(e)[:120]}")
                logger.warning("档案采集失败 %s: %s", mid, str(e)[:120])
                continue

            mgr = session.get(Manager, mid)
            mgr.fetched_at = datetime.now(UTC)

            # 直接用本次采集结果聚合（session autoflush=False，刚 add 的行
            # select 查不到；也免去一次回查）
            tenure_dicts = []
            for t in tenures:
                d = dict(t)
                d["annual_return"] = annualize(t["tenure_return_pct"], t["tenure_days"])
                tenure_dicts.append(d)
            _apply_metrics(session, mgr, tenure_dicts,
                           nav_provider=nav_provider if fetch_nav else None)
            stats["risk_computed"] += 1 if mgr.max_drawdown is not None else 0

            done += 1
            if done % BATCH_LOG_EVERY == 0:
                logger.info("M2/M3 进度 %d/%d", done, len(pending_ids))
            if run is not None:
                # 进度条按人推进：内存里每人更新，落库按 PROGRESS_COMMIT_EVERY 批
                run.completed = done
                run.failed = stats["failed"]
            if done % PROGRESS_COMMIT_EVERY == 0:
                session.commit()
            time.sleep(profile_fetch_delay_s)

        session.commit()
    except Exception as e:  # noqa: BLE001
        session.rollback()
        if run is not None:
            run.status = "error"
            run.errors = str(e)[:500]
            run.finished_at = datetime.now(UTC)
            session.commit()
        raise

    if run is not None:
        run.status = "done" if stats["failed"] == 0 else "partial"
        run.completed = done
        run.failed = stats["failed"]
        if stats["errors"]:
            # RefreshRun.errors 契约是 JSON 数组字符串（/refresh/status 用 json.loads 解析）
            run.errors = json.dumps(stats["errors"][:20], ensure_ascii=False)[:1900]
        run.finished_at = datetime.now(UTC)
        session.commit()

    logger.info("manager_refresh 完成: %s", stats)
    return stats


def _needs_fetch(session: Session, manager_id: str) -> bool:
    mgr = session.get(Manager, manager_id)
    return mgr is None or mgr.fetched_at is None


def _load_active_equity_codes(session: Session) -> set[str]:
    rows = session.execute(
        select(Fund.code).where(
            Fund.is_active == True,  # noqa: E712
            Fund.market_subtype.in_(("股票型", "混合型-偏股")),
        )
    ).scalars().all()
    return set(rows)


def _replace_tenures(session: Session, manager_id: str, tenures: list[dict[str, Any]]) -> None:
    """重写该经理的 tenures（采集幂等：每次全量替换该经理的段）。"""
    session.execute(delete(ManagerTenure).where(ManagerTenure.manager_id == manager_id))
    for t in tenures:
        session.add(ManagerTenure(
            manager_id=manager_id,
            fund_code=t["fund_code"],
            fund_name=t["fund_name"],
            fund_type=t["fund_type"],
            size_yi=t["size_yi"],
            start_date=date.fromisoformat(t["start_date"]) if t["start_date"] else None,
            end_date=date.fromisoformat(t["end_date"]) if t["end_date"] else None,
            tenure_days=t["tenure_days"],
            tenure_return=t["tenure_return_pct"],
            annual_return=annualize(t["tenure_return_pct"], t["tenure_days"]),
            is_current=t["is_current"],
        ))


def _apply_metrics(session: Session, mgr: Manager, tenures: list[dict[str, Any]],
                   nav_provider=None) -> None:
    """M3+M4：代表基金风险指标 + 聚合字段写入 managers 行。"""
    mgr.managed_fund_count = len(tenures)
    mgr.tenure_weighted_annual = weighted_annual(tenures)

    rep = pick_representative(tenures)
    if rep is None:
        return
    mgr.representative_fund = rep["fund_code"]
    mgr.longest_tenure_annual = rep["annual_return"]
    mgr.longest_tenure_years = round(rep["tenure_days"] / 365.25, 2) if rep["tenure_days"] else None

    if nav_provider is None or not rep["tenure_days"]:
        return
    try:
        # 必须切到任职窗口：基金序列是全历史，不切会把前任的回撤算到现任头上
        series = slice_series(nav_provider(rep["fund_code"]),
                              start=rep.get("start_date"), end=rep.get("end_date"))
        risk = compute_risk(series)
        if risk is not None:
            mgr.max_drawdown = risk["max_drawdown_pct"]
            mgr.sharpe = risk["sharpe"]
            mgr.calmar = risk["calmar"]
    except Exception as e:  # noqa: BLE001
        logger.warning("风险指标失败 %s(%s): %s", mgr.name, rep["fund_code"], str(e)[:100])
