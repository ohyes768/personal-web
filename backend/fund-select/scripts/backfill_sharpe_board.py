"""夏普榜单历史周回填（一次性运维脚本，容器内执行）

背景：榜单 2026-11-02 起才有发布，fund_benchmark 覆盖 2023-09-11 起的
3 年窗口 → 最早可回填 as_of=2026-09-11（week 2026-09-07）至 2026-10-26
共 8 周（2026-11-02 已 complete 不动）。

口径与每周正常发布尽量一致：
- 夏普：复用 compute_risk_metrics，r_p=净值日增长率切片 [as_of-3y, as_of]，
  r_b=基准 TRI 切片后 pct_change，r_f=空表（生产 risk_free_rate 为空 → rf=0，
  与已发布 11-02 周实际口径一致）。
- 入选谓词：与发布同一份 entry_predicate（profile v1），base 字段用当前值
  近似（历史规模/经理年限快照不存在）；dd_3y 用当前 FundPerformance 值。
- universe：stock=当前 yaml 名单；discovery-stock=市场库三段预筛的当前近似。
- 发布：publish_week_board trigger="backfill"，周键取该周五（归所在 ISO 周）。

用法（容器内 /app）：
  python scripts/backfill_sharpe_board.py --dry-run   # 只算不写
  python scripts/backfill_sharpe_board.py             # 真正发布
"""
import argparse
import sys
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

from src.data.fund_universe import load_fund_codes
from src.data.market_subtype_map import DISCOVERY_STOCK_SUBTYPES
from src.data.nav_fetcher import fetch_nav
from src.utils.config import get_stock_funds_config_path
from src.db.models import Fund, FundBenchmark, FundPerformance, MarketFundRank
from src.db.session import SessionLocal
from src.services import sharpe_board_service as sbs
from src.services.risk_service import compute_risk_metrics
from src.services.sharpe_capture import SharpeRunCapture, freeze_base_row

TZ = ZoneInfo("Asia/Shanghai")
PROFILE_VERSION = "v1"
SOURCES = ("stock", "discovery-stock")
# 回填周（周一）与该周执行时刻（对齐正常周五上午跑的节奏）
WEEK_STARTS = [date(2026, 9, 7) + timedelta(days=7 * i) for i in range(8)]


def build_universe(db, source: str) -> dict[str, dict]:
    """universe codes + base_rows（当前值近似）+ dd_3y 合并。"""
    if source == "stock":
        codes = load_fund_codes(get_stock_funds_config_path())
    else:
        profile = sbs.get_profile(source, PROFILE_VERSION)
        pre = profile["collection_prefilters"]
        subtypes = profile["market_subtypes"]
        rows = db.execute(
            select(Fund.code)
            .join(MarketFundRank, MarketFundRank.code == Fund.code)
            .where(
                Fund.market_subtype.in_(subtypes),
                Fund.size_yi >= pre["min_size_yi"],
                Fund.mgr_experience_years >= pre["min_mgr_exp"],
                MarketFundRank.ret_3y >= pre["min_ret_3y"],
            )
        ).scalars().all()
        codes = list(rows)

    base_rows: dict[str, dict] = {}
    for code in codes:
        frozen = freeze_base_row(db, code)
        if frozen is not None:
            perf = db.get(FundPerformance, code)
            frozen["dd_3y"] = perf.dd_3y if perf is not None else None
            base_rows[code] = frozen
    return base_rows


def load_nav_histories(db, codes: list[str]) -> dict[str, pd.DataFrame]:
    """每只拉一次全历史净值（日增长率），内存缓存供 8 周切片复用。"""
    out: dict[str, pd.DataFrame] = {}
    failed: list[str] = []
    for i, code in enumerate(codes, 1):
        try:
            nav = fetch_nav(code)
            if not nav.empty:
                out[code] = nav
        except Exception as e:  # noqa: BLE001
            failed.append(code)
            print(f"  nav 失败 {code}: {str(e)[:80]}", flush=True)
        if i % 50 == 0:
            print(f"  nav 进度 {i}/{len(codes)}", flush=True)
    print(f"nav 缓存：{len(out)} 成功 / {len(failed)} 失败", flush=True)
    return out


def load_bench_series(db, code: str) -> pd.Series:
    """基准 TRI 全历史 → 日收益（pct_change），回填时按 as_of 再切片。"""
    rows = db.execute(
        select(FundBenchmark.date, FundBenchmark.tri)
        .where(FundBenchmark.code == code, FundBenchmark.tri.is_not(None))
        .order_by(FundBenchmark.date)
    ).all()
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(
        [r.tri for r in rows],
        index=pd.DatetimeIndex([r.date for r in rows]),
    )
    return s.pct_change().dropna()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只计算打印，不写库")
    args = parser.parse_args()

    db = SessionLocal()
    total_written = 0
    try:
        universes: dict[str, dict[str, dict]] = {}
        nav_cache: dict[str, dict[str, pd.DataFrame]] = {}
        bench_cache: dict[str, pd.Series] = {}

        for source in SOURCES:
            print(f"== {source}：构建 universe ==", flush=True)
            base_rows = build_universe(db, source)
            universes[source] = base_rows
            print(f"universe（含 Fund 行）={len(base_rows)}", flush=True)

        # nav 缓存按 code 拉一次，两来源共享
        all_codes = sorted({c for br in universes.values() for c in br})
        print(f"== 拉取净值历史（{len(all_codes)} 只，一次性）==", flush=True)
        nav_shared = load_nav_histories(db, all_codes)

        for source in SOURCES:
            base_rows = universes[source]
            codes = list(base_rows)
            print(f"== {source}：开始逐周回填 ==", flush=True)
            for week in WEEK_STARTS:
                as_of = week + timedelta(days=4)  # 该周周五
                started_at = datetime(as_of.year, as_of.month, as_of.day, 10, 5, tzinfo=TZ)
                window_start = pd.Timestamp(as_of) - pd.Timedelta(days=365 * 3)

                risk_rows: dict[str, dict] = {}
                for code in codes:
                    nav_df = nav_shared.get(code)
                    if nav_df is None or nav_df.empty:
                        continue
                    nav = nav_df[(nav_df["净值日期"] >= window_start)
                                 & (nav_df["净值日期"] <= pd.Timestamp(as_of))]
                    r_p = nav.set_index("净值日期")["日增长率"].astype(float).div(100).dropna()
                    if code not in bench_cache:
                        bench_cache[code] = load_bench_series(db, code)
                    r_b = bench_cache[code]
                    if not r_b.empty:
                        r_b = r_b[(r_b.index >= window_start - pd.Timedelta(days=30))
                                  & (r_b.index <= pd.Timestamp(as_of))]
                    m = compute_risk_metrics(r_p, r_b, pd.Series(dtype=float))
                    if m.sharpe is None:
                        continue
                    risk_rows[code] = {
                        "sharpe": m.sharpe,
                        "returns_end_date": m.returns_end_date,
                        "sample_days": m.sample_days,
                        "calculated_at": started_at,
                        "benchmark_source": None,
                    }

                profile = sbs.get_profile(source, PROFILE_VERSION)
                capture = SharpeRunCapture(
                    run_id=f"backfill-{source}-{week.isoformat()}-{uuid.uuid4().hex[:8]}",
                    filters=profile["filters"],
                    collection_prefilters=profile["collection_prefilters"],
                    universe_codes=codes,
                    base_rows=base_rows,
                    risk_rows=risk_rows,
                )
                # 预演入选数（与 publish 同一谓词）
                predicate = sbs.entry_predicate if hasattr(sbs, "entry_predicate") else None
                from src.services.filter_service import entry_predicate
                pred = entry_predicate(**profile["filters"])
                subtype_set = set(profile["market_subtypes"]) if profile.get("market_subtypes") else None
                sel = 0
                for code in dict.fromkeys(codes):
                    r = risk_rows.get(code)
                    if r is None:
                        continue
                    if subtype_set is not None and base_rows[code].get("market_subtype") not in subtype_set:
                        continue
                    if pred({**base_rows[code], "sharpe": r["sharpe"]}):
                        sel += 1

                if args.dry_run:
                    print(f"  {source} week={week} as_of={as_of}: 有风险值={len(risk_rows)} 预计入选={sel}", flush=True)
                    continue

                from src.services.sharpe_board_service import publish_week_board
                row, written = publish_week_board(
                    db, source=source, profile_version=PROFILE_VERSION, capture=capture,
                    trigger="backfill", started_at=started_at, finished_at=started_at,
                )
                total_written += int(written)
                print(f"  {source} week={week}: status={row.status} selected={row.selected_count} written={written}", flush=True)

        print(f"完成。新写入周行数={total_written}", flush=True)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
