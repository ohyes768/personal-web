"""09-04-fix-bond-index-date-shift R1：实证 bond_composite_index_cbond 日期是否整体 -1 天。

对照沪深300（ak.stock_zh_index_daily sh000300）交易日历：
- cbond 原始日期星期分布（预期周末大量出现 = 错位证据）
- cbond 原始日期 ∩ 沪深300 交易日 的重叠数 vs (日期+1天) ∩ 沪深300 交易日
"""
from __future__ import annotations

from datetime import date, timedelta

import akshare as ak
import pandas as pd

END = date(2026, 9, 4)
START = END - timedelta(days=365 * 3)

WEEKDAY_CN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def main() -> None:
    cb = ak.bond_composite_index_cbond(indicator="财富", period="总值")
    cb["date"] = pd.to_datetime(cb["date"])
    cb = cb[(cb["date"] >= pd.Timestamp(START)) & (cb["date"] <= pd.Timestamp(END))]
    print(f"cbond 窗口 {START} ~ {END}，{len(cb)} 行，列={list(cb.columns)}")
    print("原始日期星期分布:", cb["date"].dt.weekday.map(lambda i: WEEKDAY_CN[i]).value_counts().to_dict())
    print("首尾日期:", cb["date"].iloc[0].date(), "->", cb["date"].iloc[-1].date())

    hsi = ak.stock_zh_index_daily(symbol="sh000300")
    hsi["date"] = pd.to_datetime(hsi["date"])
    hsi = hsi[(hsi["date"] >= pd.Timestamp(START)) & (hsi["date"] <= pd.Timestamp(END))]
    trade_days = set(hsi["date"])
    print(f"\n沪深300 窗口交易日 {len(trade_days)} 天，星期分布:",
          hsi["date"].dt.weekday.map(lambda i: WEEKDAY_CN[i]).value_counts().to_dict())

    d0 = set(cb["date"])
    d1 = set(cb["date"] + pd.Timedelta(days=1))
    print(f"\n原始日期 ∩ 交易日: {len(d0 & trade_days)} / {len(d0)}")
    print(f"+1 天后  ∩ 交易日: {len(d1 & trade_days)} / {len(d1)}")
    print(f"+1 天后仍落在周末的行: {sum(1 for d in d1 if d.weekday() >= 5)}")

    # 抽 3 个交易日对照：沪深300 某周一，cbond 原始是否标成周日
    sample = sorted(trade_days)[:0]
    mondays = sorted(d for d in trade_days if d.weekday() == 0)[:3]
    fridays = sorted(d for d in trade_days if d.weekday() == 4)[-3:]
    for t in mondays + fridays:
        print(f"交易日 {t.date()} ({WEEKDAY_CN[t.weekday()]}): cbond 原始含 {t.date()}? {(pd.Timestamp(t) in d0)}"
              f" | cbond 含 {t.date() - timedelta(days=1)} ({WEEKDAY_CN[(t - timedelta(days=1)).weekday()]})?"
              f" {(pd.Timestamp(t) - pd.Timedelta(days=1) in d0)}")


if __name__ == "__main__":
    main()
