"""
刷新任务：只拉 config/funds.yaml 名单（v1 不扫全市场）

- 断点续传思路：每完成一只立即 commit，进程崩溃后下次重跑
- 单只失败重试 3 次后跳过，记入 errors，不阻塞其它
- 空库可用 results_31.csv 引导（bootstrap_from_csv）
"""
import csv
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.data.fund_universe import load_fund_codes
from src.data.manager_fetcher import fetch_manager_table
from src.db.models import Fund, FundFees, FundHoldingsBond, FundPerformance, RefreshRun
from src.db.session import SessionLocal
from src.scheduler.daily_refresh import bootstrap_from_csv
from src.services.refresh_service import persist_snapshot, snapshot_fund
from src.utils.config import PROJECT_ROOT, get_stock_funds_config_path
from src.utils.logger import setup_logger

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
    """同步刷新股票型 + QDII 名单（读 config/funds_stock.yaml）。

    与 refresh_configured_funds_sync 骨架一致：
    - 单只失败重试 3 次后跳过
    - 每只立即 commit（断点续传）
    - 进度写入 RefreshRun 表
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
                    snap = snapshot_fund(code, mgr_worktime, mgr_company)
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

        _finish_run(db, run, completed, failed, errors, final_status="done")
        return {"task_id": task_id, "total": len(codes), "completed": completed, "failed": failed}
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
