"""R1 补充：+1 天后仍落周末的 20 行是什么（预期=债市调休交易日，股市休市）+ 探测中债替代源。"""
from __future__ import annotations

from datetime import date, timedelta

import akshare as ak
import pandas as pd

END = date(2026, 9, 4)
START = END - timedelta(days=365 * 3)
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def main() -> None:
    cb = ak.bond_composite_index_cbond(indicator="财富", period="总值")
    cb["date"] = pd.to_datetime(cb["date"])
    cb = cb[(cb["date"] >= pd.Timestamp(START)) & (cb["date"] <= pd.Timestamp(END))]

    hsi = ak.stock_zh_index_daily(symbol="sh000300")
    hsi["date"] = pd.to_datetime(hsi["date"])
    trade = set(hsi[(hsi["date"] >= pd.Timestamp(START))]["date"])

    shifted = cb["date"] + pd.Timedelta(days=1)
    weekend = shifted[shifted.dt.weekday >= 5]
    print(f"+1 天后落周末的 {len(weekend)} 行（真实日期=shifted，债市调休交易日）:")
    for _, s in weekend.items():
        print(f"  cbond 原始 {s.date() - timedelta(days=1)} ({WD[(s - pd.Timedelta(days=1)).weekday()]})"
              f" -> 真实 {s.date()} ({WD[s.weekday()]}) | 股市该日开市? {s in trade}")

    print("\n=== 替代源探测（dir(ak) 中债/债券指数接口）===")
    cands = [n for n in dir(ak) if any(k in n.lower() for k in ("bond", "cbond"))]
    for n in sorted(cands):
        print(" ", n)


if __name__ == "__main__":
    main()
