"""
全市场基金名单 refresh：upsert Fund.name / market_subtype / market_type / fund_type / mgr_*

阶段 0（09-08）：除原 4 字段外，再写入：
- fund_type ← ak.fund_name_em() 「基金类型」字段（不覆盖已有非空值）
- mgr_name ← ak.fund_manager_em() 按 现任基金代码 反查，经理名用 `、` 拼接
- mgr_company ← 多经理的第一位所属公司
- mgr_days / mgr_experience_years ← 多经理中从业最短（min，保守口径，历史保留）
- mgr_days_max / mgr_experience_years_max ← 多经理中从业最长（max，筛选口径）

为什么同时存 min 和 max（09-xx 缺陷修复）：
共管基金里「老将 + 新人」极其常见（全市场 7868 只共管基金中 4443 只，占 56.5%）。
原先只有 min，导致「22 年老将 + 3 年新人」被记成 3 年，min_mgr_exp=5 直接误杀
（债基 universe 1519 只、股基市场 526 只）。取 max 表示「该基金有资深经理在管」，
符合"跟着谁买"的实际判断；min 保留给历史口径与集中度诊断。

关键约束：
- fund_type：仅在已有值为空时才覆盖（避免覆盖掉老 L2 雪球细分类）
- is_active：不动（akshare 无法判定清盘）
- 业绩 / 费率 / 持仓 / 风险指标：其他 refresh 流程负责

按 batch commit（默认 500/批），减少 SQLite lock；RefreshRun 表记录进度。
"""
import json
from datetime import UTC, datetime
from typing import Any, Optional

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db.models import Fund, RefreshRun
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_refresh")

BATCH_SIZE = 500


def refresh(
    session: Session,
    df: pd.DataFrame,
    task_id: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
    mgr_by_code: Optional[dict[str, list[dict[str, Any]]]] = None,
    existing_fund_types: Optional[dict[str, str]] = None,
) -> dict:
    """upsert DataFrame 到 funds 表，返回 {total, inserted, updated, failed, errors, task_id}。

    Args:
        session: SQLAlchemy session
        df: DataFrame 必须含列：code / name / market_subtype / market_type
            （fund_type / mgr_* 字段可选；不提供则用预加载 dict 或跳过写入）
        task_id: 非空时同步更新 RefreshRun 进度
        batch_size: 每批 commit 行数
        mgr_by_code: 经理表预聚合（{code: [{name, company, days}, ...]}）。
                传入则用传入值；None 则不写 mgr_*（向后兼容老调用方）。
        existing_fund_types: 预加载的已有 fund_type（{code: fund_type}）。
                传入则在 fund_type 写入处先查表预加载；None 则按需单行 get。
                仅当 df 含 'fund_type' 列时才生效。

    task_id 非空时同步更新 RefreshRun 进度。
    """
    has_fund_type = "fund_type" in df.columns
    write_mgr = mgr_by_code is not None

    total = len(df)
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

    for start in range(0, total, batch_size):
        batch = df.iloc[start:start + batch_size]
        codes = batch["code"].tolist()
        existing_codes = {
            row for row in session.execute(
                select(Fund.code).where(Fund.code.in_(codes))
            ).scalars().all()
        }

        # fund_type 不覆盖已有值：批量预加载已有 fund_type
        existing_fund_type_map: dict[str, str] = {}
        if has_fund_type and existing_codes:
            if existing_fund_types:
                # 使用调用方预加载的（避免每批重复查询）
                existing_fund_type_map = {
                    c: existing_fund_types.get(c, "")
                    for c in existing_codes
                }
            else:
                existing_fund_type_map = dict(session.execute(
                    select(Fund.code, Fund.fund_type).where(Fund.code.in_(codes))
                ).all())

        now = datetime.now(UTC)

        for row in batch.itertuples(index=False):
            code = row.code
            try:
                # mgr_* 字段聚合（取自 mgr_by_code，与 df 行无关）
                mgr_name = mgr_company = None
                mgr_days = mgr_exp_years = None
                mgr_days_max = mgr_exp_years_max = None
                mgrs: list[dict[str, Any]] = []
                if write_mgr:
                    mgrs = mgr_by_code.get(code) or []
                    if mgrs:
                        mgr_name = "、".join(m["name"] for m in mgrs) or None
                        # mgr_company：取第一位经理所属公司（避免空字符串顶掉 None）
                        first_co = next(
                            (m["company"] for m in mgrs if m.get("company")), None
                        )
                        mgr_company = first_co or None
                        # min = 最保守（历史口径）；max = 有资深经理在管（筛选口径）
                        days_list = [int(m["days"]) for m in mgrs if m.get("days") is not None]
                        if days_list:
                            mgr_days = min(days_list)
                            mgr_days_max = max(days_list)
                            mgr_exp_years = round(mgr_days / 365.25, 2)
                            mgr_exp_years_max = round(mgr_days_max / 365.25, 2)

                if code in existing_codes:
                    update_values: dict[str, Any] = dict(
                        name=row.name,
                        market_subtype=row.market_subtype,
                        market_type=row.market_type,
                        updated_at=now,
                    )
                    # fund_type：仅当新值非空 + 已有值为空 才覆盖
                    if has_fund_type:
                        new_ft = (row.fund_type or "").strip()
                        old_ft = (existing_fund_type_map.get(code) or "").strip()
                        if new_ft and not old_ft:
                            update_values["fund_type"] = new_ft
                    # ⚠ 只有**确实有经理记录**时才写 mgr_*。
                    # 无条件写会把「akshare 经理表里没这只基金」变成「把已有值清成 NULL」——
                    # yaml 名单基金的 mgr 来自雪球 basic 接口（更准），不能被 akshare 的
                    # 缺记录抹掉（回归：11-14 全量刷新修复）。
                    if write_mgr and mgrs:
                        update_values.update(
                            mgr_name=mgr_name,
                            mgr_company=mgr_company,
                            mgr_days=mgr_days,
                            mgr_experience_years=mgr_exp_years,
                            mgr_days_max=mgr_days_max,
                            mgr_experience_years_max=mgr_exp_years_max,
                        )
                    session.execute(
                        update(Fund).where(Fund.code == code).values(**update_values)
                    )
                    updated += 1
                else:
                    # 新增：fund_type 取 df 新值；mgr_* 取 mgr_by_code
                    insert_fund_type = (row.fund_type if has_fund_type else "") or ""
                    new_fund = Fund(
                        code=code,
                        name=row.name,
                        market_subtype=row.market_subtype,
                        market_type=row.market_type,
                        fund_type=insert_fund_type,
                        is_active=True,
                        updated_at=now,
                    )
                    if write_mgr and mgrs:
                        new_fund.mgr_name = mgr_name
                        new_fund.mgr_company = mgr_company
                        new_fund.mgr_days = mgr_days
                        new_fund.mgr_experience_years = mgr_exp_years
                        new_fund.mgr_days_max = mgr_days_max
                        new_fund.mgr_experience_years_max = mgr_exp_years_max
                    session.add(new_fund)
                    inserted += 1
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
        "market_refresh: total=%d inserted=%d updated=%d failed=%d (mgr_written=%s, ft_written=%s)",
        total, inserted, updated, failed, write_mgr, has_fund_type,
    )
    return {
        "task_id": task_id,
        "total": total,
        "inserted": inserted,
        "updated": updated,
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
