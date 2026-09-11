"""
市场 tab 全量数据 refresh（profile-driven 流水线 + 分阶段重算 codes）

profile（pipeline_profile 参数）：
  "stock" — 6 阶段：L0 universe / L1 rank / L2 size / L3 nav / L4 risk / L5 achievement
  "bond"  — 5 阶段：L0 universe / L1 rank / L2 size / L3 nav / L6 fees_holdings（跳过 L4/L5）
    跳过 L4/L5 原因：债基详情页不消费 risk_service 6 指标、不展示同类排名
    （RowDetailDrawerBond.tsx 未导入 RiskMetricsGrid / achievement_ranks）。
    跳过的同时也用 L6_fees_holdings 替代——债基详情页消费 fees/holdings 数据
    （fund_fees / fund_holdings_bond 表），复用 fetch_fees + fetch_bond_hold + persist_snapshot 写入。
    老债基三分法（refresh_configured_funds_sync）路径独立处理，与本 pipeline 无关。

阶段：
  L0 universe 全市场名单（ak.fund_name_em，5 秒）
  L1 rankhandler 业绩（ak.fund_open_fund_rank_em，50 秒）
  L2 size_yi + age_years（雪球优先 + 东财 msm fallback，单只 ~0.4s，~8 分钟）
  L3 日频净值 + dd/ret（22 分钟）
  L4 业绩比较基准 + 风险指标（44 分钟，stock only）
  L5 同类排名（fund_achievement_xq，22 分钟，stock only）
  L6 fees + bond holdings（5 worker 并发，bond only；复用 fetch_fees + fetch_bond_hold + persist_snapshot）

分阶段重算 codes（关键：避免首次空跑）：
  初始：仅预筛 1（mgr_exp，funds 表已有字段）
  L1 后：+预筛 2（ret_3y + nav_date，market_fund_rank 表已填）
  L2 后：+预筛 3（size_yi，funds 表已填）→ 最终 L3/L4/L5 用这个 codes

仅接 3 个用户参数：
  - min_mgr_exp：经理从业 ≥ W 年（预筛 1，funds.mgr_experience_years）
  - min_ret_3y：近 3 年涨跌幅 ≥ X%（预筛 2，market_fund_rank.ret_3y）
  - min_size_yi：规模 ≥ Y 亿（预筛 3，funds.size_yi）

后端常量：
  - 净值新鲜度 ≤ MAX_NAV_STALE_DAYS = 14 天（不再接用户参数）
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


def _fetch_one_fees_holdings(code: str, year: str) -> dict:
    """单只 fees + holdings 抓取，结果装入 persist_snapshot 期望的 dict 形态。

    复用 fetch_fees / fetch_bond_hold / analyze_holdings；不调 snapshot_fund 避免
    重复拉 basic/nav/performance（L0/L1/L2/L3 已写过 funds/market_nav 表）。

    失败容错：fetch_bond_hold 内部已吞异常（返回 []），空表 → holdings=None 跳过 persist。
    fetch_fees 失败抛异常 → 由调用方 `_stage_l6_fees_holdings` 外层捕获，计入 failed。
    """
    from src.data.fee_fetcher import fetch_fees
    from src.data.holdings_fetcher import analyze_holdings, fetch_bond_hold

    out: dict = {"code": code, "achievement": None}  # achievement=None 让 persist_snapshot 跳过
    fees = fetch_fees(code)
    out["fees"] = fees if fees else {}
    tables = fetch_bond_hold(code, year)
    if tables:
        out["holdings"] = {
            "report_date": date(int(year), 12, 31),
            **analyze_holdings(tables),
        }
    else:
        out["holdings"] = None
    return out


def _stage_l6_fees_holdings(d: Session, codes: list[str], task_id: str) -> dict:
    """L6 fees + bond holdings（仅 profile='bond' 触发）。

    复用 fetch_fees + fetch_bond_hold + analyze_holdings + persist_snapshot。
    ThreadPoolExecutor(max_workers=5) 对齐 market_nav_fetcher.MAX_WORKERS（东财反爬限流）。
    单只失败仅入账 errors，不重试、不阻塞其他（激进跳过策略——东财接口反爬重试收益低）。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from src.services.refresh_service import persist_snapshot

    # 防御性二次过滤：理论上 codes_after_l2 已是债基 universe，但兜底
    # （未来 profile 扩展时这层过滤防呆；当前 universe_filter 已收紧到债基）
    bond_codes = list(
        d.execute(
            select(Fund.code).where(
                Fund.code.in_(codes),
                Fund.market_subtype.in_(DISCOVERY_BOND_SUBTYPES),
            )
        ).scalars().all()
    )
    if not bond_codes:
        logger.info("[market_full] L6 无债基 universe，跳过")
        return {"task_id": f"{task_id}_L6", "total": 0, "completed": 0, "failed": 0, "errors": []}

    # 默认抓上一年报（对齐 snapshot_fund:47 内部 `holdings_year = str(ref.year - 1)`）
    holdings_year = str(date.today().year - 1)
    completed = failed = 0
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            ex.submit(_fetch_one_fees_holdings, code, holdings_year): code
            for code in bond_codes
        }
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                snap = fut.result()
                # fees 或 holdings 任一有值就 persist（避免空 dict 触发空 upsert）
                if snap.get("fees") or snap.get("holdings"):
                    persist_snapshot(d, snap)
                    d.commit()  # 每只立即提交（断点续传，对齐老路径行为）
                completed += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                err_msg = str(e)[:120]
                errors.append(f"fees_holdings:{code}: {err_msg}")
                logger.warning("L6 %s 失败: %s", code, err_msg)

    logger.info(
        "market_full L6: total=%d completed=%d failed=%d",
        len(bond_codes), completed, failed,
    )
    return {
        "task_id": f"{task_id}_L6",
        "total": len(bond_codes),
        "completed": completed,
        "failed": failed,
        "errors": errors,
    }


def refresh_market_full_sync(
    universe_filter: Optional[list[str]] = None,
    min_ret_3y: Optional[float] = None,
    min_size_yi: Optional[float] = None,
    min_mgr_exp: Optional[float] = None,
    preset_task_id: Optional[str] = None,
    pipeline_profile: str = "stock",
) -> dict:
    """市场 tab 全量数据 refresh（profile-driven 流水线 + 分阶段重算 codes）。

    pipeline_profile:
      "stock" — 6 阶段（L0..L5）
      "bond"  — 5 阶段（跳 L4 risk + L5 achievement；L6_fees_holdings 替代——债基详情页消费 fees/holdings）

    仅接 3 个用户参数：
      - min_mgr_exp：经理从业 ≥ W 年（预筛 1，funds.mgr_experience_years）
      - min_ret_3y：近 3 年涨跌幅 ≥ X%（预筛 2，market_fund_rank.ret_3y）
      - min_size_yi：规模 ≥ Y 亿（预筛 3，funds.size_yi）

    后端常量：
      - 净值新鲜度 ≤ MAX_NAV_STALE_DAYS = 14 天（不再接用户参数）

    分阶段重算 codes（避免首次空跑）：
      初始 → L0/L1 → 重算 +预筛 2 → L2 → 重算 +预筛 3 → L3/L4/L5
      这样 L0/L1/L2 完成后才应用 L1/L2 数据依赖的预筛，L3-L5 拿到真实命中。
    """
    if pipeline_profile not in ("stock", "bond"):
        raise ValueError(f"pipeline_profile must be 'stock' or 'bond', got {pipeline_profile!r}")

    # bond profile 跳过 L4/L5 后单次刷新 ~100min → ~30min（44+22 分钟风险/排名 IO 省下），
    # 用 L6_fees_holdings 补上详情页消费的 fees/holdings 数据写入。
    if pipeline_profile == "bond":
        stages_per_code = 5  # L0/L1/L2/L3/L6_fees_holdings
    else:
        stages_per_code = 6  # L0/L1/L2/L3/L4/L5

    task_id = preset_task_id or str(_uuid.uuid4())
    db = SessionLocal()
    try:
        # 分阶段重算 codes（关键：每次都看最新数据，避免首次空跑）
        #   初始：仅预筛 1（mgr_exp，funds 表已有字段）
        #   L1 后：+预筛 2（ret_3y + nav_date，market_fund_rank 表已填）
        #   L2 后：+预筛 3（size_yi，funds 表已填）→ 最终 L3/L4/L5 用这个 codes
        codes = _load_market_universe(
            db,
            universe_filter,
            min_mgr_exp=min_mgr_exp,
        )
        logger.info(
            "[market_full] task=%s profile=%s 初始 universe=%d (filter=%s min_mgr_exp=%s)",
            task_id, pipeline_profile, len(codes), universe_filter, min_mgr_exp,
        )

        # 创建主 task 的 RefreshRun 记录（前端轮询用）
        from src.db.models import RefreshRun
        from datetime import UTC, datetime
        main_run = RefreshRun(
            task_id=task_id, status="running",
            total=len(codes) * stages_per_code if codes else stages_per_code,
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

        # L1 后重算 codes（加预筛 2：ret_3y + nav_date）
        # L1 写入 market_fund_rank 全市场数据，预筛 2 现在能命中
        codes_after_l1 = _load_market_universe(
            db,
            universe_filter,
            min_mgr_exp=min_mgr_exp,
            min_ret_3y=min_ret_3y,
            max_nav_stale_days=MAX_NAV_STALE_DAYS,
        )
        logger.info(
            "[market_full] task=%s L1 后 universe=%d (min_ret_3y=%s max_nav_stale_days=%s)",
            task_id, len(codes_after_l1), min_ret_3y, MAX_NAV_STALE_DAYS,
        )
        codes = codes_after_l1

        # L2 size_yi + age_years（东财移动端 msm 接口，单只 ~0.4s）
        # 仅对 L1 预筛后剩下的 codes 跑（避免拉全 universe 浪费）
        def _stage_l2(d):
            rows = fetch_market_size(codes)
            return refresh_market_size_db(d, rows, task_id=f"{task_id}_L2")

        stage_results["L2_size"] = _run_stage(db, task_id, "L2_size",
                                              len(codes), _stage_l2)
        _update_main_progress(len(codes),
                              failed=stage_results["L2_size"].get("result", {}).get("failed", 0))

        # L2 后重算 codes（加预筛 3：size_yi >= Y 亿）
        # L2 已把 size_yi 写入 funds 表，预筛 3 现在能命中
        codes_after_l2 = _load_market_universe(
            db,
            universe_filter,
            min_mgr_exp=min_mgr_exp,
            min_ret_3y=min_ret_3y,
            max_nav_stale_days=MAX_NAV_STALE_DAYS,
            min_size_yi=min_size_yi,
        )
        logger.info(
            "[market_full] task=%s profile=%s L2 后 universe=%d (最终 codes min_size_yi=%s stages=%d)",
            task_id, pipeline_profile, len(codes_after_l2), min_size_yi, stages_per_code,
        )
        codes = codes_after_l2
        # 更新主 task 总进度（按 profile 动态算：stock=6, bond=4）
        main_run.total = len(codes) * stages_per_code if codes else stages_per_code
        db.commit()

        # L3 日频净值 + dd/ret
        def _stage_l3(d):
            nav_data = fetch_market_nav(codes)
            return refresh_market_nav_db(d, nav_data, task_id=f"{task_id}_L3")

        stage_results["L3_nav"] = _run_stage(db, task_id, "L3_nav",
                                              len(codes), _stage_l3)
        _update_main_progress(len(codes),
                              failed=stage_results["L3_nav"].get("result", {}).get("failed", 0))

        if pipeline_profile == "bond":
            # L6 fees + bond holdings（仅 bond profile）
            # 复用 fetch_fees / fetch_bond_hold fetcher + persist_snapshot 写入路径
            # 单只失败仅入账 errors，不阻塞其他（对齐 market_nav_fetcher.MAX_WORKERS = 5 限流）
            def _stage_l6(d):
                return _stage_l6_fees_holdings(d, codes, task_id=task_id)

            stage_results["L6_fees_holdings"] = _run_stage(db, task_id, "L6_fees_holdings",
                                                          len(codes), _stage_l6)
            _update_main_progress(len(codes),
                                  failed=stage_results["L6_fees_holdings"].get("result", {}).get("failed", 0))
            logger.info("[market_full] task=%s profile=bond 跳过 L4 risk + L5 achievement，跑 L6 fees_holdings",
                       task_id)

            # bond profile：L4/L5 跳过
            skip_risk_actual = True
            skip_achievement_actual = True
        else:
            skip_risk_actual = False
            skip_achievement_actual = False

        # L4 业绩比较基准 + 风险指标（stock only；bond profile 跳过）
        if not skip_risk_actual:
            def _stage_l4(d):
                return refresh_market_risk_db(d, codes, task_id=f"{task_id}_L4")

            stage_results["L4_risk"] = _run_stage(db, task_id, "L4_risk",
                                                    len(codes), _stage_l4)
            _update_main_progress(len(codes),
                                  failed=stage_results["L4_risk"].get("result", {}).get("failed", 0))
        else:
            logger.info("[market_full] task=%s profile=bond 跳过 L4 risk 阶段", task_id)

        # L5 同类排名（ak.fund_individual_achievement_xq，每只单只拉 ~1.5s）
        # stock only；bond profile 跳过（前端债基详情页不展示同类排名）
        if not skip_achievement_actual:
            def _stage_l5(d):
                ach_data = fetch_market_achievement(codes)
                return refresh_market_achievement(d, ach_data, task_id=f"{task_id}_L5")

            stage_results["L5_achievement"] = _run_stage(db, task_id, "L5_achievement",
                                                        len(codes), _stage_l5)
            _update_main_progress(len(codes),
                                  failed=stage_results["L5_achievement"].get("result", {}).get("failed", 0))
        else:
            logger.info("[market_full] task=%s profile=bond 跳过 L5 achievement 阶段", task_id)

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
