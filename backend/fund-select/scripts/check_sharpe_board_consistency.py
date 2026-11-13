"""夏普周榜口径一致性核对 v2（只读）：完整计数 + 按周分解 + 缓存复用。

真值周：
- 2026-09-07 / 2026-10-26：原版回填周（当时用 DB TRI，已被滚动刷新裁剪）
- 2026-11-02：scheduled 生产周（当时用 DB TRI，覆盖完整）
变体：
- A_syn：扩展合成 TRI + 头垫切片（= 本次 ext 回填的路径，全 3 年窗）
- B_db：库内 DB TRI 不切片（= 生产路径）
"""
import pickle
import statistics
from collections import Counter
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select

from src.data.benchmark_fetcher import clear_index_cache, fetch_benchmark_tri
from src.data.nav_fetcher import fetch_nav
from src.db.models import FundBenchmark, RiskFreeRate, SharpeBoardObservation, SharpeBoardWeek
from src.db.session import SessionLocal
from src.services.risk_service import compute_risk_metrics

TARGET_WEEKS = [date(2026, 9, 7), date(2026, 10, 26), date(2026, 11, 2)]
NAV_CACHE = "/tmp/chk_nav.pkl"
BENCH_CACHE = "/tmp/chk_bench.pkl"


def get_nav(codes):
    try:
        with open(NAV_CACHE, "rb") as f:
            c = pickle.load(f)
        if isinstance(c, dict) and c:
            print(f"nav 缓存命中 {len(c)} 只")
            return c
    except Exception:
        pass
    out, empty, fail = {}, [], []
    for i, code in enumerate(codes, 1):
        try:
            df = fetch_nav(code)
            (out.__setitem__(code, df) if not df.empty else empty.append(code))
        except Exception:
            fail.append(code)
        if i % 100 == 0:
            print(f"  nav {i}/{len(codes)}", flush=True)
    print(f"nav: {len(out)} 非空 / {len(empty)} 空 / {len(fail)} 异常")
    with open(NAV_CACHE, "wb") as f:
        pickle.dump(out, f)
    return out


def main():
    db = SessionLocal()
    try:
        print("risk_free rows =", db.query(RiskFreeRate).count())
        truth = {}
        for week in TARGET_WEEKS:
            for w in db.execute(select(SharpeBoardWeek).where(
                    SharpeBoardWeek.week_start == week)).scalars().all():
                for o in db.execute(select(SharpeBoardObservation).where(
                        SharpeBoardObservation.week_id == w.id)).scalars().all():
                    truth[(w.source, week, o.code)] = {
                        "sharpe": o.sharpe, "sample_days": o.sample_days}
        print(f"真值观测 {len(truth)} 条，覆盖 {len({c for _, _, c in truth})} 只 code")
        codes = sorted({c for _, _, c in truth})
        nav = get_nav(codes)

        tri_codes = set(db.execute(select(FundBenchmark.code).where(
            FundBenchmark.tri.is_not(None)).distinct()).scalars().all())
        targets = sorted(set(codes) & tri_codes)
        try:
            with open(BENCH_CACHE, "rb") as f:
                bench_A = pickle.load(f)
            print(f"bench 缓存命中 {len(bench_A)} 只")
        except Exception:
            ext_start = date(2020, 9, 8)
            print(f"合成扩展 TRI {len(targets)} 只 ...", flush=True)
            clear_index_cache()
            bench_A = {}
            for i, code in enumerate(targets, 1):
                try:
                    df, _ = fetch_benchmark_tri(code, ext_start, date.today())
                    if not df.empty:
                        s = pd.Series(df["tri"].astype(float).values,
                                      index=pd.DatetimeIndex(df["date"].values))
                        bench_A[code] = s.pct_change().dropna()
                except Exception as e:  # noqa: BLE001
                    print(f"  合成失败 {code}: {str(e)[:60]}")
                if i % 100 == 0:
                    print(f"  bench {i}/{len(targets)}", flush=True)
            with open(BENCH_CACHE, "wb") as f:
                pickle.dump(bench_A, f)
        bench_B = {}
        for code in codes:
            rows = db.execute(select(FundBenchmark.date, FundBenchmark.tri).where(
                FundBenchmark.code == code, FundBenchmark.tri.is_not(None))
                .order_by(FundBenchmark.date)).all()
            if rows:
                bench_B[code] = pd.Series(
                    [r.tri for r in rows],
                    index=pd.DatetimeIndex([r.date for r in rows])).pct_change().dropna()

        report: dict[tuple, Counter] = {}
        diffs_all: dict[tuple, list] = {}
        for (source, week, code), t in truth.items():
            as_of = week + timedelta(days=4)
            ws = pd.Timestamp(as_of) - pd.Timedelta(days=365 * 3)
            nav_df = nav.get(code)
            for variant, bench in (("A_syn", bench_A), ("B_db", bench_B)):
                key = (source, week, variant)
                report.setdefault(key, Counter())
                diffs_all.setdefault(key, [])
                if nav_df is None:
                    report[key]["nav缺失"] += 1
                    continue
                w = nav_df[(nav_df["净值日期"] >= ws) & (nav_df["净值日期"] <= pd.Timestamp(as_of))]
                r_p = w.set_index("净值日期")["日增长率"].astype(float).div(100).dropna()
                r_b = bench.get(code, pd.Series(dtype=float))
                if variant == "A_syn" and not r_b.empty:
                    r_b = r_b[(r_b.index >= ws - pd.Timedelta(days=30)) & (r_b.index <= pd.Timestamp(as_of))]
                m = compute_risk_metrics(r_p, r_b, pd.Series(dtype=float))
                if m.sharpe is None:
                    report[key]["重算无值"] += 1
                    continue
                d = abs(m.sharpe - t["sharpe"])
                if d < 1e-9:
                    report[key]["逐位一致"] += 1
                elif d < 0.005:
                    report[key]["小差异"] += 1
                else:
                    report[key]["大差异"] += 1
                diffs_all[key].append(d)
                if m.sample_days != t["sample_days"]:
                    report[key]["sample天数不同"] += 1

        print("\n===== 按周/来源分解 =====")
        for (source, week, variant), c in sorted(report.items()):
            ds = diffs_all[(source, week, variant)]
            med = statistics.median(ds) if ds else float("nan")
            print(f"{source:15s} {week} {variant:5s}: {dict(c)}  diff中位数={med:.5f} 最大={max(ds) if ds else 0:.5f}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    main()
