"""09-04-benchmark-yaml-coverage R5：benchmark TRI + risk 指标全量重刷（股票宇宙）。

参照 scheduler/tasks.py refresh_stock 的收尾两步；单只失败重试。
输出重刷前后 source 分布对比。
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "fund-select"))

from sqlalchemy import text  # noqa: E402

from src.data.benchmark_fetcher import clear_index_cache  # noqa: E402
from src.data.fund_universe import resolve_universe_codes  # noqa: E402
from src.db.models import FundBenchmark  # noqa: E402
from src.db.session import SessionLocal  # noqa: E402
from src.scheduler.tasks import _refresh_fund_benchmarks  # noqa: E402
from src.utils.logger import setup_logger  # noqa: E402

logger = setup_logger("fund-select.refresh_0904")


def source_dist(db) -> dict[str, int]:
    rows = db.execute(
        text("SELECT source, COUNT(DISTINCT code) AS n FROM fund_benchmark GROUP BY source")
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def main() -> None:
    db = SessionLocal()
    try:
        codes = resolve_universe_codes("stock")
        before = source_dist(db)
        print(f"股票宇宙 {len(codes)} 只")
        print("重刷前 source 分布:", dict(sorted(before.items(), key=lambda kv: -kv[1])))

        clear_index_cache()
        bench_failed = []
        for attempt in range(1, 4):
            try:
                bench_failed = _refresh_fund_benchmarks(db, codes)
                break
            except Exception as e:  # noqa: BLE001
                print(f"benchmark 重刷第 {attempt} 次失败: {type(e).__name__}: {str(e)[:120]}")
                time.sleep(3)
        print(f"benchmark 失败 {len(bench_failed)} 只: {bench_failed[:10]}")

        from src.services.risk_service import refresh_fund_risks
        risk_failed = []
        for attempt in range(1, 4):
            try:
                risk_failed = refresh_fund_risks(db, codes)
                break
            except Exception as e:  # noqa: BLE001
                print(f"risk 重刷第 {attempt} 次失败: {type(e).__name__}: {str(e)[:120]}")
                time.sleep(3)
        print(f"risk 失败 {len(risk_failed)} 只: {risk_failed[:10]}")

        after = source_dist(db)
        print("\n=== source 分布对比（distinct code）===")
        for key in sorted(set(before) | set(after)):
            print(f"  {key}: {before.get(key, 0)} -> {after.get(key, 0)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
