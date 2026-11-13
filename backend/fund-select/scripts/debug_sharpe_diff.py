"""定位夏普重算差异的来源（只读）。对少量 code 打印全部中间量。"""
import json
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select

from src.data.benchmark_fetcher import clear_index_cache, fetch_benchmark_tri
from src.data.nav_fetcher import fetch_nav
from src.db.models import FundBenchmark, FundRiskMetrics, SharpeBoardObservation, SharpeBoardWeek
from src.db.session import SessionLocal
from src.services.risk_service import compute_risk_metrics

CASES = [
    ("stock", date(2026, 9, 7), "096001"),   # A_syn 大差异（疑似 QDII）
    ("stock", date(2026, 9, 7), "006593"),
    ("stock", date(2026, 11, 2), "006282"),  # B_db 大差异
    ("stock", date(2026, 11, 2), "016452"),
    ("discovery-stock", date(2026, 11, 2), None),  # 取该周第一只观测
]


def joined_info(r_p, r_b, label):
    if r_b is not None and len(r_b.dropna()) >= 250:
        j = pd.concat([r_p.rename("p"), r_b.rename("b")], axis=1, join="inner").dropna()
    else:
        j = r_p.to_frame("p")
    excess = j["p"]
    sharpe = None
    if len(j) > 1 and float(excess.std(ddof=1)) > 0:
        sharpe = float(excess.mean()) / float(excess.std(ddof=1)) * (252 ** 0.5)
    print(f"    [{label}] joined={len(j)} head={j.index.min().date()} tail={j.index.max().date()} sharpe={sharpe}")
    return j


def main():
    db = SessionLocal()
    try:
        print("risk_free rows:", db.query(__import__('src.db.models', fromlist=['RiskFreeRate']).RiskFreeRate).count())
        clear_index_cache()
        for source, week, code in CASES:
            w = db.execute(select(SharpeBoardWeek).where(
                SharpeBoardWeek.source == source, SharpeBoardWeek.week_start == week)).scalars().first()
            if w is None:
                print(f"== {source} {week}: 无周行"); continue
            obs_rows = db.execute(select(SharpeBoardObservation).where(
                SharpeBoardObservation.week_id == w.id).order_by(SharpeBoardObservation.code)).scalars().all()
            if code is None:
                code = obs_rows[0].code
            o = next((x for x in obs_rows if x.code == code), None)
            if o is None:
                print(f"== {source} {week} {code}: 无观测"); continue
            as_of = week + timedelta(days=4)
            ws = pd.Timestamp(as_of) - pd.Timedelta(days=365 * 3)
            print(f"== {source} {week} {code} as_of={as_of} 窗口起点={ws.date()}")
            print(f"    库内观测: sharpe={o.sharpe:.6f} sample_days={o.sample_days} "
                  f"returns_end={o.returns_end_date} evidence={o.evidence_json[:180]}")
            frm = db.get(FundRiskMetrics, code)
            if frm is not None:
                print(f"    FundRiskMetrics: sharpe={frm.sharpe} sample_days={frm.sample_days} as_of={frm.as_of_date}")
            # DB TRI 行范围
            brows = db.execute(select(FundBenchmark.date).where(
                FundBenchmark.code == code, FundBenchmark.tri.is_not(None)).order_by(FundBenchmark.date)).all()
            tri_min = brows[0][0] if brows else None
            tri_max = brows[-1][0] if brows else None
            print(f"    DB TRI rows={len(brows)} range=[{tri_min}, {tri_max}]")
            # nav
            nav = fetch_nav(code)
            nav_w = nav[(nav["净值日期"] >= ws) & (nav["净值日期"] <= pd.Timestamp(as_of))]
            r_p = nav_w.set_index("净值日期")["日增长率"].astype(float).div(100).dropna()
            print(f"    r_p: n={len(r_p)} range=[{r_p.index.min().date()}, {r_p.index.max().date()}]")
            # 变体 B：DB TRI 不切片（生产口径）
            if brows:
                s = pd.Series([db.execute(select(FundBenchmark.tri).where(
                    FundBenchmark.code == code, FundBenchmark.date == r[0])).scalars().first() for r in brows],
                    index=pd.DatetimeIndex([r[0] for r in brows]))
                r_b_b = s.pct_change().dropna()
                joined_info(r_p, r_b_b, "B_db")
                # 生产 r_p 窗口口径（run_date-3y）：周六运行 start=run-3y
                prod_start = pd.Timestamp(as_of) + pd.Timedelta(days=1) - pd.Timedelta(days=365 * 3)
                r_p_prod = nav[nav["净值日期"] >= prod_start].set_index("净值日期")["日增长率"].astype(float).div(100).dropna()
                print(f"    r_p(生产口径 start={prod_start.date()}): n={len(r_p_prod)} "
                      f"range=[{r_p_prod.index.min().date()}, {r_p_prod.index.max().date()}]")
                joined_info(r_p_prod, r_b_b, "B_db+生产r_p窗口")
            # 变体 A：扩展合成 TRI
            ext_start = date(2020, 9, 8)
            df, src = fetch_benchmark_tri(code, ext_start, date.today())
            if not df.empty:
                sA = pd.Series(df["tri"].astype(float).values, index=pd.DatetimeIndex(df["date"].values))
                r_b_a = sA.pct_change().dropna()
                r_b_a = r_b_a[(r_b_a.index >= ws - pd.Timedelta(days=30)) & (r_b_a.index <= pd.Timestamp(as_of))]
                print(f"    合成TRI source={src} 切片后 returns n={len(r_b_a)} head={r_b_a.index.min().date() if len(r_b_a) else None}")
                joined_info(r_p, r_b_a, "A_syn")
            else:
                print(f"    合成TRI: 空 (source={src}) → 无基准路径")
                joined_info(r_p, None, "A_syn无基准")
    finally:
        db.close()


if __name__ == "__main__":
    main()
