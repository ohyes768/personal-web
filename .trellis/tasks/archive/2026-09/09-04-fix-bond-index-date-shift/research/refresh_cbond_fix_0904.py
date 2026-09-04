"""09-04-fix-bond-index-date-shift R3：全量股票宇宙 benchmark + risk 重刷（中债换源后）。

参照 09-04-benchmark-yaml-coverage/research/refresh_benchmarks_0904.py，另记录：
- 公式含中债成分（ak_symbol=CBA00301）的受影响基金数
- 重刷前后每只基金 3 年窗口 TRI 累计对比（抽差值最大者作为样例）
- source 分布对比
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
ROOT = REPO / "backend" / "fund-select"
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.data.benchmark_fetcher import clear_index_cache, parse_formula  # noqa: E402
from src.data.fund_basic_fetcher import fetch_basic  # noqa: E402
from src.data.fund_universe import resolve_universe_codes  # noqa: E402
from src.db.session import SessionLocal  # noqa: E402
from src.scheduler.tasks import _refresh_fund_benchmarks  # noqa: E402
from src.services.risk_service import refresh_fund_risks  # noqa: E402

END = date.today()
START = END - timedelta(days=365 * 3)


def source_dist(db) -> dict[str, int]:
    rows = db.execute(
        text("SELECT source, COUNT(DISTINCT code) AS n FROM fund_benchmark GROUP BY source")
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def tri_snapshot(db) -> pd.DataFrame:
    """每只基金：TRI 行数 / NULL 行数 / 3 年窗口累计收益 last/first - 1 / 末行日期"""
    rows = db.execute(text("SELECT code, date, tri FROM fund_benchmark")).fetchall()
    df = pd.DataFrame(rows, columns=["code", "date", "tri"])
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= pd.Timestamp(START)) & (df["date"] <= pd.Timestamp(END))]
    out = []
    for code, g in df.groupby("code"):
        g = g.sort_values("date").dropna(subset=["tri"])
        cum = (g["tri"].iloc[-1] / g["tri"].iloc[0] - 1) if len(g) >= 2 else None
        out.append({"code": code, "n": len(g), "cum": cum,
                    "last_date": g["date"].iloc[-1] if len(g) else None})
    return pd.DataFrame(out).set_index("code")


def affected_by_cbond(codes: list[str]) -> list[str]:
    """公式含中债成分（映射到 CBA00301）的基金 = 本次修复真正影响的宇宙"""
    hit = []
    for code in codes:
        try:
            info = fetch_basic(code)
        except Exception as e:  # noqa: BLE001
            print(f"  fetch_basic {code} 失败: {type(e).__name__} {str(e)[:60]}")
            continue
        raw = str(info.get("业绩比较基准") or "")
        if any(c.ak_symbol == "CBA00301" for c in parse_formula(raw)):
            hit.append(code)
    return hit


def retry(fn, label: str, *args):
    for attempt in range(1, 4):
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001
            print(f"{label} 第 {attempt} 次失败: {type(e).__name__}: {str(e)[:120]}")
            time.sleep(5)
    return []


def main() -> None:
    db = SessionLocal()
    try:
        codes = resolve_universe_codes("stock")
        print(f"股票宇宙 {len(codes)} 只")
        before = tri_snapshot(db)
        before_src = source_dist(db)

        print("统计公式含中债成分的基金（逐只联网拉基础信息）...")
        hit = affected_by_cbond(codes)
        print(f"受影响基金（公式含 CBA00301 成分）{len(hit)} 只: {hit}")

        clear_index_cache()
        bench_failed = retry(_refresh_fund_benchmarks, "benchmark", db, codes)
        print(f"benchmark 失败 {len(bench_failed)} 只: {bench_failed[:10]}")
        risk_failed = retry(refresh_fund_risks, "risk", db, codes)
        print(f"risk 失败 {len(risk_failed)} 只: {risk_failed[:10]}")

        after = tri_snapshot(db)
        after_src = source_dist(db)

        print("\n=== source 分布对比（distinct code）===")
        for key in sorted(set(before_src) | set(after_src)):
            print(f"  {key}: {before_src.get(key, 0)} -> {after_src.get(key, 0)}")

        common = before.join(after, lsuffix="_before", rsuffix="_after", how="outer")
        changed = common[
            common["cum_before"].notna() & common["cum_after"].notna()
            & ((common["cum_before"] - common["cum_after"]).abs() > 1e-9)
        ]
        null_after = common[common["n_after"].isna() | (common["n_after"] == 0)]
        print(f"\nTRI 行存在且 3 年累计变化的基金: {len(changed)} 只（TRI 全 NULL 的: {len(null_after)} 只）")
        changed2 = changed.copy()
        changed2["delta_pp"] = (changed2["cum_after"] - changed2["cum_before"]) * 100
        changed2 = changed2.sort_values("delta_pp", key=lambda s: s.abs(), ascending=False)
        print("Δ累计 TOP5（百分点，正=中债周五收益补回后基准更高）:")
        print(changed2[["cum_before", "cum_after", "delta_pp"]].head(5).to_string())

        in_hit = changed2[changed2.index.isin(hit)]
        if len(in_hit):
            top = in_hit.iloc[0]
            print(f"\n样例（受影响基金中 Δ 最大）{in_hit.index[0]}: "
                  f"3 年累计 {top['cum_before'] * 100:.2f}% -> {top['cum_after'] * 100:.2f}% "
                  f"(Δ {top['delta_pp']:+.2f}pp), 末行日期 {top['last_date_after'].date()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
