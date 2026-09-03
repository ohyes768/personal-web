"""批量探测候选指数的 akshare 数据源（09-04-benchmark-yaml-coverage R2）。

收录标准：拉到日线 + 末条数据 >= end - 10 天（非停更）。
每个候选按序试多接口，报「末条日期 / 行数 / 是否达标」。
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "fund-select"))

import akshare as ak  # noqa: E402
import pandas as pd  # noqa: E402

TODAY = date.today()
END = TODAY.strftime("%Y%m%d")
START = (TODAY - timedelta(days=365 * 3 + 30)).strftime("%Y%m%d")
FRESH = pd.Timestamp(TODAY) - pd.Timedelta(days=10)

DATE_COLS = ("date", "日期")
CLOSE_COLS = ("close", "收盘", "收盘指数", "收盘价")


def _pick(df: pd.DataFrame, cols: tuple[str, ...]) -> str | None:
    return next((c for c in df.columns if c in cols), None)


def call(fn: str, symbol: str) -> pd.DataFrame:
    if fn == "csindex":
        return ak.stock_zh_index_hist_csindex(symbol=symbol, start_date=START, end_date=END)
    if fn == "sw":
        return ak.index_hist_sw(symbol=symbol, period="day")
    if fn == "cni":
        return ak.index_hist_cni(symbol=symbol, start_date=START, end_date=END)
    if fn == "hk_em":
        return ak.stock_hk_index_daily_em(symbol=symbol)
    if fn == "hk_sina":
        return ak.stock_hk_index_daily_sina(symbol=symbol)
    if fn == "tx":
        return ak.stock_zh_index_daily_tx(symbol=symbol)
    if fn == "sina":
        return ak.stock_zh_index_daily(symbol=symbol)
    raise ValueError(fn)


# (yaml 候选名, [(接口, symbol), ...])
PROBES: list[tuple[str, list[tuple[str, str]]]] = [
    ("中证A50", [("csindex", "930050"), ("sina", "sh930050")]),
    ("中证红利低波", [("csindex", "H30269")]),
    ("中证港股通高股息投资", [("csindex", "930914")]),
    ("中证中金优选300", [("csindex", "931069")]),
    ("中证东方红优势成长", [("csindex", "931579")]),
    ("中证东方红红利低波动", [("csindex", "931446")]),
    ("中证港股通央企红利", [("csindex", "931233")]),
    ("中证科创创业50", [("csindex", "931643"), ("sina", "sh931643")]),
    ("中证国信价值", [("csindex", "931052")]),
    ("中证内地资源", [("csindex", "000944"), ("sina", "sh000944")]),
    ("中证高端装备制造", [("csindex", "930599")]),
    ("中证800相对成长", [("csindex", "H30357"), ("tx", "sh000917")]),
    ("中证沪港深高股息精选", [("csindex", "930836")]),
    ("中证移动互联网", [("csindex", "399970"), ("sina", "sz399970"), ("tx", "sz399970")]),
    ("中证互联网", [("csindex", "H30535")]),
    ("中证海外中国互联网", [("csindex", "H11136")]),
    ("中证香港银行投资", [("csindex", "930792")]),
    ("国证自由现金流", [("cni", "980092")]),
    ("申万医药生物", [("sw", "801150")]),
    ("申万制造业", [("sw", "801110")]),
    ("恒生综合", [("tx", "hkHSCI"), ("hk_em", "HSCI"), ("hk_sina", "HSCI")]),
]


def main() -> None:
    for name, tries in PROBES:
        results = []
        for fn, sym in tries:
            try:
                df = call(fn, sym)
                dcol, ccol = _pick(df, DATE_COLS), _pick(df, CLOSE_COLS)
                if dcol is None or ccol is None:
                    results.append(f"{fn}:{sym}=列缺失{list(df.columns)[:6]}")
                    continue
                last = pd.to_datetime(df[dcol]).max()
                fresh = "FRESH" if last >= FRESH else "STALE"
                results.append(f"{fn}:{sym}=末条{last.date()} n={len(df)} {fresh}")
            except Exception as e:  # noqa: BLE001
                results.append(f"{fn}:{sym}=FAIL({type(e).__name__}:{str(e)[:60]})")
            time.sleep(0.6)
        print(f"{name}\n    " + "\n    ".join(results))


if __name__ == "__main__":
    main()
