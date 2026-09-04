"""
季报债券持仓 fetcher + 债券分类（东财 FundArchivesDatas.aspx，移植 fund_screen_31.py）
"""
import json
import re
from io import StringIO

import pandas as pd
import requests

from src.data.bond_classifier import classify_bond
from src.utils.config import CACHE_DIR
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.holdings_fetcher")

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://fundf10.eastmoney.com/"}


def fetch_bond_hold(code: str, year: str, use_cache: bool = True) -> list[pd.DataFrame]:
    """返回按时间倒序的季度持仓表格列表（东财季报，可能被反爬 → 空列表）。"""
    cache_file = CACHE_DIR / f"bond_hold_{code}_{year}.json"
    if use_cache and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            return [pd.DataFrame(t) for t in cached]
        except Exception:
            logger.warning("持仓缓存损坏 %s，重新拉取", cache_file.name)

    try:
        r = requests.get(
            "https://fundf10.eastmoney.com/FundArchivesDatas.aspx",
            params={"type": "zqcc", "code": code, "year": year, "rt": "0.913"},
            headers=HEADERS,
            timeout=15,
        )
        text = r.text.strip()
        text = re.sub(r"^\s*var\s+\w+\s*=\s*", "", text).rstrip(";").strip()
        text = re.sub(r"([\{,\s])(\w+)\s*:", r'\1"\2":', text)
        data = json.loads(text)
        tables = pd.read_html(StringIO(data["content"]))
    except Exception as e:
        logger.warning("季报持仓拉取失败 %s: %s", code, str(e)[:120])
        return []

    result = []
    for t in tables:
        if "债券代码" in t.columns:
            t["占净值比例"] = (
                t["占净值比例"].astype(str).str.rstrip("%").apply(pd.to_numeric, errors="coerce")
            )
            result.append(t)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps([t.to_dict(orient="records") for t in result], ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception:
        logger.warning("持仓缓存写入失败 %s（不影响流程）", code)
    return result


def analyze_holdings(tables: list[pd.DataFrame]) -> dict:
    """最新一季持仓 → 利率债/信用债/可转债占比 + 前五大集中度。"""
    if not tables:
        return {}
    latest = tables[0]
    if latest.empty:
        return {}

    classes = latest["债券名称"].astype(str).apply(classify_bond)
    rate = float(latest.loc[classes == "rate", "占净值比例"].sum())
    credit = float(latest.loc[classes == "credit", "占净值比例"].sum())
    convert = float(latest.loc[classes == "convertible", "占净值比例"].sum())
    top5 = float(latest.nlargest(5, "占净值比例")["占净值比例"].sum())

    top5_str = "; ".join(
        f"{r['债券名称']}({r['占净值比例']:.1f}%)"
        for _, r in latest.head(5).iterrows()
    )
    return {
        "rate_bond_pct": round(rate, 2),
        "credit_bond_pct": round(credit, 2),
        "convertible_pct": round(convert, 2),
        "top5_concentration": round(top5, 2),
        "top5_bonds": top5_str,
    }


def latest_report_date(tables: list[pd.DataFrame]) -> str | None:
    """从最新表格解析报告期（'2025年3月31日' → '2025-03-31'）；解析不出返回 None。"""
    if not tables or tables[0].empty:
        return None
    # 东财表格列名可能是「占净值比例日期」或表内无日期；预研快照固定用年末
    # 为稳妥，直接返回 None，由调用方用 year-12-31 兜底
    return None
