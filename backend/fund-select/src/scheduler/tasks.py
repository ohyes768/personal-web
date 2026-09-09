"""
刷新任务：只拉 config/funds.yaml 名单（v1 不扫全市场）
+
全市场基金名单 refresh（market tab 专用）：ak.fund_name_em() 一次拉全市场

- 断点续传思路：每完成一只立即 commit，进程崩溃后下次重跑
- 单只失败重试 3 次后跳过，记入 errors，不阻塞其它
- 空库可用 results_31.csv 引导（bootstrap_from_csv）
"""
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.data.fund_universe import load_fund_codes
from src.data.manager_fetcher import fetch_manager_table
from src.data.market_universe_fetcher import fetch_market_universe
from src.db.models import Fund, FundBenchmark, RefreshRun, RiskFreeRate
from src.db.session import SessionLocal
from src.scheduler.daily_refresh import bootstrap_from_csv
from src.services.market_universe_refresh import refresh as refresh_market_db
from src.services.refresh_service import persist_snapshot, snapshot_fund
from src.utils.config import PROJECT_ROOT, get_stock_funds_config_path
from src.utils.logger import setup_logger

# market_full_pipeline 单独 import（避免循环依赖）
def _import_full_pipeline():
    from src.services.market_full_pipeline import refresh_market_full_sync
    return refresh_market_full_sync

logger = setup_logger("fund-select.tasks")

# 预研 CSV（空库引导）
BOOTSTRAP_CSV = PROJECT_ROOT.parent / "results_31.csv"
# 预研 cache 目录（费率/持仓兜底）
LEGACY_CACHE = PROJECT_ROOT.parent / "cache"

MAX_RETRY_PER_FUND = 3


def refresh_configured_funds_sync(
    limit: int | None = None, use_cache: bool = True, preset_task_id: str | None = None
) -> dict:
    """同步刷新配置名单。返回 {task_id, total, completed, failed}。"""
    task_id = preset_task_id or str(uuid.uuid4())
    codes = load_fund_codes()
    if limit:
        codes = codes[:limit]

    db = SessionLocal()
    try:
        run = RefreshRun(task_id=task_id, status="running", total=len(codes))
        db.add(run)
        db.commit()

        if not codes:
            _finish_run(db, run, errors=["配置名单为空"])
            return {"task_id": task_id, "total": 0, "completed": 0, "failed": 0}

        # 经理表一次拉取
        mgr_worktime, mgr_company = fetch_manager_table(use_cache=use_cache)

        completed = 0
        failed = 0
        errors: list[str] = []
        for i, code in enumerate(codes, 1):
            snap = None
            last_err = None
            for attempt in range(1, MAX_RETRY_PER_FUND + 1):
                try:
                    snap = snapshot_fund(code, mgr_worktime, mgr_company)
                    break
                except Exception as e:
                    last_err = str(e)[:150]
                    logger.warning("[%d/%d] %s 第 %d 次失败: %s", i, len(codes), code, attempt, last_err)
            if snap is None:
                failed += 1
                errors.append(f"{code}: {last_err}")
                _update_progress(db, run, completed, failed, errors)
                continue

            persist_snapshot(db, snap)
            db.commit()  # 每只立即提交（断点续传）
            completed += 1
            _update_progress(db, run, completed, failed, errors)
            logger.info("[%d/%d] ✓ %s %s", i, len(codes), code, snap.get("name", "")[:20])

        _finish_run(db, run, completed, failed, errors, final_status="done")
        return {"task_id": task_id, "total": len(codes), "completed": completed, "failed": failed}
    finally:
        db.close()


def _update_progress(db: Session, run: RefreshRun, completed: int, failed: int, errors: list[str]) -> None:
    run.completed = completed
    run.failed = failed
    if errors:
        run.errors = _errors_json(errors)
    db.commit()


def refresh_stock_funds_sync(
    limit: int | None = None,
    use_cache: bool = True,
    preset_task_id: str | None = None,
) -> dict:
    """同步刷新 funds_stock.yaml 名单（股票型 / QDII / 混合型 全名单）。

    与 refresh_configured_funds_sync 骨架一致：
    - 单只失败重试 3 次后跳过
    - 每只立即 commit（断点续传）
    - 进度写入 RefreshRun 表
    - 差异：fetch_holdings=False（股票宇宙不拉债券季报，债基 tab 才消费持仓）
            + fetch_ranking=True（funds_stock.yaml 全名单抓雪球业绩排名，含混合型）
    """
    task_id = preset_task_id or str(uuid.uuid4())
    codes = load_fund_codes(get_stock_funds_config_path())
    if limit:
        codes = codes[:limit]

    db = SessionLocal()
    try:
        run = RefreshRun(task_id=task_id, status="running", total=len(codes))
        db.add(run)
        db.commit()

        if not codes:
            _finish_run(db, run, errors=["股票基金配置名单为空"])
            return {"task_id": task_id, "total": 0, "completed": 0, "failed": 0}

        mgr_worktime, mgr_company = fetch_manager_table(use_cache=use_cache)

        completed = 0
        failed = 0
        errors: list[str] = []
        for i, code in enumerate(codes, 1):
            snap = None
            last_err = None
            for attempt in range(1, MAX_RETRY_PER_FUND + 1):
                try:
                    snap = snapshot_fund(code, mgr_worktime, mgr_company, fetch_holdings=False, fetch_ranking=True)
                    break
                except Exception as e:
                    last_err = str(e)[:150]
                    logger.warning("[stock %d/%d] %s 第 %d 次失败: %s", i, len(codes), code, attempt, last_err)
            if snap is None:
                failed += 1
                errors.append(f"{code}: {last_err}")
                _update_progress(db, run, completed, failed, errors)
                continue

            persist_snapshot(db, snap)
            db.commit()
            completed += 1
            _update_progress(db, run, completed, failed, errors)
            logger.info("[stock %d/%d] ✓ %s %s", i, len(codes), code, snap.get("name", "")[:20])

        # 业绩基准 TRI（phase2-A）+ 风险指标（phase2-B）：主循环后统一跑，单只失败不影响整批
        bench_failed = _refresh_fund_benchmarks(db, codes)
        errors.extend(bench_failed)

        from src.services.risk_service import refresh_fund_risks
        risk_failed = refresh_fund_risks(db, codes)
        errors.extend(risk_failed)

        _finish_run(db, run, completed, failed, errors, final_status="done")
        return {"task_id": task_id, "total": len(codes), "completed": completed, "failed": failed}
    finally:
        db.close()


def _refresh_fund_benchmarks(db: Session, codes: list[str]) -> list[str]:
    """全量刷新 fund_benchmark（delete + insert，仿 _replace_achievement 模式）。

    窗口近 3 年（与 dd_3y 口径一致）；指数级缓存让 143 只只拉 ~35 次指数日线。
    无基准字段的基金写一行 tri=NULL（phase2-B 读到即跳过该基金指标计算）。
    QDII/互认基金基准公式多无免费数据源（MSCI/标普全球等），fallback 出的中证800
    是错误口径 → 跳过合成直接写 tri=NULL（PRD 09-03-qdii-skip-benchmark）；
    判定口径同 filter_service 的 exclude_qdii。
    """
    from src.data.benchmark_fetcher import clear_index_cache, fetch_benchmark_tri

    skip_codes = {
        code for (code,) in db.query(Fund.code).filter(
            Fund.code.in_(codes),
            # 用 market_subtype 判定 QDII（funds.fund_type 字段从 fetch_market_universe 没填过，
            # 全为空字符串；market_subtype 是 akshare 原始 27 个枚举值，准确）
            or_(Fund.market_subtype.like("QDII%"),
                Fund.market_subtype == "互认基金"),
        ).all()
    }
    if skip_codes:
        logger.info("[benchmark] 跳过 %d 只 QDII/互认基金基准合成", len(skip_codes))

    clear_index_cache()
    end = date.today()
    start = end - timedelta(days=365 * 3)
    bench_errors: list[str] = []
    for i, code in enumerate(codes, 1):
        try:
            db.query(FundBenchmark).filter(FundBenchmark.code == code).delete()
            if code in skip_codes:
                db.add(FundBenchmark(code=code, date=end, tri=None, source="skipped:qdii"))
                db.commit()
                continue
            df, source = fetch_benchmark_tri(code, start, end)
            if df.empty:
                db.add(FundBenchmark(code=code, date=end, tri=None, source=source))
            else:
                db.add_all([
                    FundBenchmark(code=code, date=r["date"].date(), tri=float(r["tri"]), source=source)
                    for _, r in df.iterrows()
                ])
            db.commit()
            if i % 20 == 0:
                logger.info("[benchmark %d/%d] 缓存进度", i, len(codes))
        except Exception as e:  # noqa: BLE001  单只失败不阻塞
            db.rollback()
            bench_errors.append(f"benchmark:{code}: {str(e)[:120]}")
            logger.warning("[benchmark %d/%d] %s 失败: %s", i, len(codes), code, str(e)[:120])
    return bench_errors


def refresh_risk_free_rate_sync() -> dict:
    """独立刷新 risk_free_rate（与基金无关，一次拉全历史）。"""
    from src.data.risk_free_fetcher import fetch_risk_free_rate

    end = date.today()
    start = date(1990, 1, 1)
    db = SessionLocal()
    try:
        df = fetch_risk_free_rate(start, end)
        source = df.attrs.get("source", "bond_zh_us_rate_2y")
        db.query(RiskFreeRate).delete()
        db.add_all([
            RiskFreeRate(date=r["date"].date(), rate=float(r["rate"]), source=source)
            for _, r in df.iterrows()
        ])
        db.commit()
        logger.info("[risk_free] 刷新 %d 行", len(df))
        return {"rows": len(df)}
    finally:
        db.close()


def refresh_market_universe_sync(preset_task_id: str | None = None) -> dict:
    """全市场基金名单 refresh（market tab 数据源）。

    1. 调 ak.fund_name_em() 一次拉全市场 ~1 万只
    2. upsert Fund 表的 name / market_type，不动 fund_type / is_active / 业绩数据
    3. RefreshRun 记录进度

    返回 refresh() 的结果字典：{task_id, total, inserted, updated, failed, errors}。
    """
    import json as _json

    task_id = preset_task_id or str(uuid.uuid4())
    db = SessionLocal()
    run: RefreshRun | None = None
    try:
        run = RefreshRun(task_id=task_id, status="running", total=0)
        db.add(run)
        db.commit()

        df = fetch_market_universe()
        result = refresh_market_db(db, df, task_id=task_id)
        logger.info(
            "[market_universe] task=%s total=%d inserted=%d updated=%d failed=%d",
            task_id, result["total"], result["inserted"], result["updated"], result["failed"],
        )
        return result
    except Exception as e:
        logger.exception("refresh_market_universe_sync 失败: %s", str(e)[:200])
        if run is not None:
            run.status = "error"
            run.finished_at = datetime.now(UTC)
            run.errors = _json.dumps([str(e)[:200]], ensure_ascii=False)
            db.commit()
        raise
    finally:
        db.close()


def _finish_run(db: Session, run: RefreshRun, completed: int = 0, failed: int = 0,
                errors: list[str] | None = None, final_status: str = "done") -> None:
    run.status = final_status
    run.completed = completed
    run.failed = failed
    run.finished = datetime.now(UTC)
    if errors:
        run.errors = _errors_json(errors)
    db.commit()


def _errors_json(errors: list[str]) -> str:
    import json
    return json.dumps(errors, ensure_ascii=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="刷新配置名单基金")
    parser.add_argument("--once", action="store_true", help="立即执行一次")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 只（调试用）")
    parser.add_argument("--no-cache", action="store_true", help="忽略本地缓存强制联网")
    parser.add_argument("--bootstrap", action="store_true", help="空库时用预研 CSV 引导")
    args = parser.parse_args()

    if args.bootstrap:
        n = bootstrap_from_csv()
        print(f"CSV 引导完成：{n} 只入库")
    if args.once:
        result = refresh_configured_funds_sync(limit=args.limit, use_cache=not args.no_cache)
        print(f"刷新完成: {result}")
