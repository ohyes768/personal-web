"""AC 抽查：000051 source / 新收录指数基金 TRI 与真实指数同向且量级合理。"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "fund-select"))

import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.data.fund_universe import resolve_universe_codes  # noqa: E402
from src.db.session import SessionLocal  # noqa: E402

END = date.today()
START = END - timedelta(days=365 * 3)

# (code, 基金说明, 指数名, 指数 symbol, source, 指数权重)
SAMPLES = [
    ("021208", "中证A50 ETF联接", "中证A50", "930050", "stock_zh_index_hist_csindex", 0.95),
    ("014339", "申万制造业基金", "申万制造业", "801110", "index_hist_sw", 0.75),
    ("018387", "港股通高股息", "中证港股通高股息投资", "930914", "stock_zh_index_hist_csindex", 0.95),
]


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT DISTINCT source FROM fund_benchmark WHERE code='000051'")).fetchall()
        print("000051 source:", [r[0] for r in rows])

        import akshare as ak
        for code, desc, idx_name, sym, source, w in SAMPLES:
            rows = db.execute(text(
                "SELECT date, tri FROM fund_benchmark WHERE code=:c ORDER BY date"),
                {"c": code}).fetchall()
            tri = pd.DataFrame(rows, columns=["date", "tri"])
            tri_cum = tri["tri"].iloc[-1] / tri["tri"].iloc[0] - 1
            if source == "stock_zh_index_hist_csindex":
                idx = ak.stock_zh_index_hist_csindex(
                    symbol=sym, start_date=START.strftime("%Y%m%d"), end_date=END.strftime("%Y%m%d"))
                idx.columns = [c for c in idx.columns]
                s = pd.Series(idx["收盘"].values, index=pd.to_datetime(idx["日期"]))
            else:  # sw
                idx = ak.index_hist_sw(symbol=sym, period="day")
                s = pd.Series(idx["收盘"].values, index=pd.to_datetime(idx["日期"]))
            s = s[(s.index >= pd.Timestamp(START)) & (s.index <= pd.Timestamp(END))]
            idx_cum = s.iloc[-1] / s.iloc[0] - 1
            same_dir = (tri_cum >= 0) == (idx_cum >= 0)
            print(f"{code} {desc} | TRI 3y={tri_cum:+.1%} | {idx_name} 3y={idx_cum:+.1%} "
                  f"| 权重{w:.0%} | 同向={same_dir} | 量级比={tri_cum / idx_cum:.2f}")
        # 库内风险指标抽查：新收录基金基准相关指标是否有值
        for code, *_ in SAMPLES:
            r = db.execute(text(
                "SELECT code, alpha, ir, alpha_ir, excess_3y, sample_days FROM fund_risk_metrics WHERE code=:c"),
                {"c": code}).fetchone()
            print("risk:", r)
    finally:
        db.close()


if __name__ == "__main__":
    main()
